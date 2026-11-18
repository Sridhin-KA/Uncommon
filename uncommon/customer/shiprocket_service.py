
import logging
import re
from decimal import Decimal

import requests

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from .models import ShiprocketShipment


logger = logging.getLogger(__name__)


# ==========================================================
# SHIPROCKET CONFIGURATION
# ==========================================================

SHIPROCKET_BASE_URL = (
    "https://apiv2.shiprocket.in/v1/external"
)

TOKEN_CACHE_KEY = "shiprocket_api_token"
TOKEN_CACHE_TIMEOUT = 9 * 24 * 60 * 60


# ==========================================================
# 1. GENERATE SHIPROCKET TOKEN
# ==========================================================

def generate_shiprocket_token():

    email = getattr(settings, "SHIPROCKET_EMAIL", None)
    password = getattr(settings, "SHIPROCKET_PASSWORD", None)

    if not email or not password:
        raise ValueError(
            "Shiprocket credentials are missing."
        )

    response = requests.post(
        f"{SHIPROCKET_BASE_URL}/auth/login",
        json={
            "email": email,
            "password": password,
        },
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    token = data.get("token")

    if not token:
        raise ValueError(
            f"Shiprocket token not received. Response: {data}"
        )

    cache.set(
        TOKEN_CACHE_KEY,
        token,
        TOKEN_CACHE_TIMEOUT,
    )

    logger.info(
        "Shiprocket authentication successful."
    )

    return token


# ==========================================================
# 2. GET SHIPROCKET TOKEN
# ==========================================================

def get_shiprocket_token():

    token = cache.get(TOKEN_CACHE_KEY)

    if token:
        return token

    return generate_shiprocket_token()


# ==========================================================
# 3. SHIPROCKET API REQUEST
# ==========================================================

def shiprocket_request(method, endpoint, **kwargs):

    token = get_shiprocket_token()

    headers = kwargs.pop("headers", {}).copy()

    headers["Authorization"] = f"Bearer {token}"

    url = (
        f"{SHIPROCKET_BASE_URL}/"
        f"{endpoint.lstrip('/')}"
    )

    response = requests.request(
        method,
        url,
        headers=headers,
        timeout=30,
        **kwargs,
    )

    # Refresh token if expired
    if response.status_code == 401:

        logger.warning(
            "Shiprocket token expired. Refreshing token."
        )

        cache.delete(TOKEN_CACHE_KEY)

        token = generate_shiprocket_token()

        headers["Authorization"] = f"Bearer {token}"

        response = requests.request(
            method,
            url,
            headers=headers,
            timeout=30,
            **kwargs,
        )

    # Handle API errors
    if not response.ok:

        logger.error(
            "Shiprocket API error: %s",
            response.text,
        )

        response.raise_for_status()

    # IMPORTANT:
    # Cancellation API can return HTTP 204 with no body.
    if response.status_code == 204 or not response.content:
        return {}

    try:
        return response.json()

    except ValueError:
        raise ValueError(
            "Shiprocket returned an invalid JSON response: "
            f"{response.text}"
        )


# ==========================================================
# 4. CLEAN CUSTOMER PHONE NUMBER
# ==========================================================

def clean_phone(phone):

    digits = re.sub(
        r"\D",
        "",
        str(phone or ""),
    )

    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]

    if len(digits) != 10:
        raise ValueError(
            "Customer phone number must contain 10 digits."
        )

    return digits


# ==========================================================
# 5. PARSE SHIPPING ADDRESS
# ==========================================================

def parse_shipping_address(order):

    """
    Expected format:

    Customer Name
    9876543210
    House Name, Street
    Kochi, Kerala - 682001
    """

    lines = [
        line.strip()
        for line in (
            order.shipping_address or ""
        ).splitlines()
        if line.strip()
    ]

    if len(lines) < 4:
        raise ValueError(
            "Invalid shipping address format. "
            "Expected name, phone, address and city/state/pincode."
        )

    customer_name = lines[0]

    phone = clean_phone(lines[1])

    address = ", ".join(lines[2:-1])

    location_line = lines[-1]

    match = re.match(
        r"^(.*?),\s*(.*?)\s*-\s*(\d{6})$",
        location_line,
    )

    if not match:
        raise ValueError(
            "Invalid city/state/pincode format. "
            "Expected: Kochi, Kerala - 682001"
        )

    city = match.group(1).strip()
    state = match.group(2).strip()
    pincode = match.group(3)

    if not address:
        raise ValueError(
            "Customer address is missing."
        )

    name_parts = customer_name.split(maxsplit=1)

    first_name = name_parts[0]

    last_name = (
        name_parts[1]
        if len(name_parts) > 1
        else ""
    )

    return {
        "first_name": first_name,
        "last_name": last_name,
        "phone": phone,
        "address": address,
        "city": city,
        "state": state,
        "pincode": int(pincode),
    }


# ==========================================================
# 6. BUILD SHIPROCKET ORDER PAYLOAD
# ==========================================================

def build_shiprocket_order_payload(order):

    if not order.items.exists():
        raise ValueError(
            "Cannot create Shiprocket order without order items."
        )

    address = parse_shipping_address(order)

    order_items = []

    total_weight = Decimal("0")

    parcel_length = Decimal("0")
    parcel_breadth = Decimal("0")
    parcel_height = Decimal("0")

    item_subtotal = Decimal("0")

    for item in order.items.select_related(
        "product"
    ).all():

        product = item.product

        quantity = int(item.quantity)

        if quantity <= 0:
            raise ValueError(
                f"Invalid quantity for product {product.pk}."
            )

        price = Decimal(str(item.price))

        weight = Decimal(
            str(product.weight or "0.500")
        )

        length = Decimal(
            str(product.length or "20")
        )

        breadth = Decimal(
            str(product.breadth or "15")
        )

        height = Decimal(
            str(product.height or "10")
        )

        if min(
            weight,
            length,
            breadth,
            height,
        ) <= 0:
            raise ValueError(
                f"Invalid shipping dimensions for product "
                f"{product.pk}."
            )

        order_items.append({
            "name": str(product.product_name)[:200],
            "sku": str(product.pk),
            "units": quantity,
            "selling_price": float(price),
        })

        item_subtotal += price * quantity

        total_weight += weight * quantity

        parcel_length = max(
            parcel_length,
            length,
        )

        parcel_breadth = max(
            parcel_breadth,
            breadth,
        )

        # Assumes products are stacked vertically.
        parcel_height += height * quantity

    # Minimum package dimensions and weight
    total_weight = max(
        total_weight,
        Decimal("0.100"),
    )

    parcel_length = max(
        parcel_length,
        Decimal("1"),
    )

    parcel_breadth = max(
        parcel_breadth,
        Decimal("1"),
    )

    parcel_height = max(
        parcel_height,
        Decimal("1"),
    )

    pickup_location = getattr(
        settings,
        "SHIPROCKET_PICKUP_LOCATION",
        "",
    )

    if not pickup_location:
        raise ValueError(
            "SHIPROCKET_PICKUP_LOCATION is missing in settings.py."
        )

    customer = order.customer

    payment_method = (
        "COD"
        if order.payment_method == "COD"
        else "Prepaid"
    )

    item_subtotal = item_subtotal.quantize(
        Decimal("0.01")
    )

    payload = {

        "order_id": str(order.order_number),

        "order_date": timezone.localtime(
            order.created_at
        ).strftime("%Y-%m-%d %H:%M"),

        "pickup_location": pickup_location,

        "billing_customer_name": address["first_name"],

        "billing_last_name": address["last_name"],

        "billing_address": address["address"],

        "billing_city": address["city"],

        "billing_pincode": address["pincode"],

        "billing_state": address["state"],

        "billing_country": "India",

        "billing_email": customer.email or "",

        "billing_phone": address["phone"],

        "shipping_is_billing": True,

        "order_items": order_items,

        "payment_method": payment_method,

        "sub_total": float(item_subtotal),

        "length": float(parcel_length),

        "breadth": float(parcel_breadth),

        "height": float(parcel_height),

        "weight": float(total_weight),
    }

    return payload


# ==========================================================
# 7. CREATE SHIPROCKET ORDER
# ==========================================================

def create_shiprocket_order(order):

    """
    Create Shiprocket order after admin confirms the order.

    Returns:
        True  - Successfully created or already exists.
        False - Creation failed.
    """

    if order.status != "CONFIRMED":

        logger.warning(
            "Shiprocket skipped. Order %s is not confirmed.",
            order.order_number,
        )

        return False

    shipment = ShiprocketShipment.objects.filter(
        order=order
    ).first()

    # Prevent duplicate Shiprocket orders.
    if shipment and shipment.shiprocket_order_id:

        logger.info(
            "Shiprocket order already exists for %s.",
            order.order_number,
        )

        return True

    shipment, created = (
        ShiprocketShipment.objects.get_or_create(
            order=order
        )
    )

    try:

        payload = build_shiprocket_order_payload(order)

        shipment.request_data = payload
        shipment.error_message = ""

        shipment.save(
            update_fields=[
                "request_data",
                "error_message",
                "updated_at",
            ]
        )

        logger.info(
            "Sending order %s to Shiprocket.",
            order.order_number,
        )

        response_data = shiprocket_request(
            "POST",
            "orders/create/adhoc",
            json=payload,
        )

        logger.info(
            "Shiprocket response for %s: %s",
            order.order_number,
            response_data,
        )

        shiprocket_order_id = response_data.get(
            "order_id"
        )

        shipment_id = response_data.get(
            "shipment_id"
        )

        if not shiprocket_order_id or not shipment_id:

            raise ValueError(
                "Shiprocket did not return order_id or shipment_id. "
                f"Response: {response_data}"
            )

        with transaction.atomic():

            shipment = (
                ShiprocketShipment.objects.select_for_update()
                .get(pk=shipment.pk)
            )

            shipment.shiprocket_order_id = str(
                shiprocket_order_id
            )

            shipment.shipment_id = str(
                shipment_id
            )

            shipment.status = "CREATED"

            shipment.response_data = response_data

            shipment.error_message = ""

            shipment.save()

        logger.info(
            "Shiprocket order created successfully: %s",
            order.order_number,
        )

        return True

    except Exception as exc:

        logger.exception(
            "Shiprocket order creation failed for %s.",
            order.order_number,
        )

        shipment.status = "FAILED"

        shipment.error_message = str(exc)

        shipment.save(
            update_fields=[
                "status",
                "error_message",
                "updated_at",
            ]
        )

        return False


# ==========================================================
# 8. ASSIGN SHIPROCKET AWB
# ==========================================================

def assign_shiprocket_awb(order):

    """
    Assign courier and generate AWB for an existing
    Shiprocket order.

    Returns True on success, False on failure.
    """

    shipment = ShiprocketShipment.objects.filter(
        order=order
    ).first()

    if not shipment:

        logger.warning(
            "No Shiprocket shipment found for order %s.",
            order.order_number,
        )

        return False

    if not shipment.shipment_id:

        logger.warning(
            "Shiprocket shipment ID missing for order %s.",
            order.order_number,
        )

        return False

    # Prevent duplicate AWB requests.
    if shipment.awb_code:

        logger.info(
            "AWB already assigned for order %s.",
            order.order_number,
        )

        return True

    try:

        response_data = shiprocket_request(
            "POST",
            "courier/assign/awb",
            json={
                "shipment_id": int(
                    shipment.shipment_id
                ),
            },
        )

        logger.info(
            "Shiprocket AWB response for %s: %s",
            order.order_number,
            response_data,
        )

        # Correctly handle nested Shiprocket response:
        # response -> data -> awb_code

        details = response_data.get(
            "response"
        ) or response_data

        if isinstance(details, dict):

            details = (
                details.get("data")
                or details
            )

        if isinstance(details, list):

            details = (
                details[0]
                if details
                else {}
            )

        if not isinstance(details, dict):

            raise ValueError(
                f"Unexpected AWB response: {response_data}"
            )

        awb_code = (
            details.get("awb_code")
            or details.get("awb")
        )

        courier_name = (
            details.get("courier_name")
            or details.get("courier")
            or ""
        )

        tracking_url = (
            details.get("tracking_url")
            or details.get("track_url")
            or ""
        )

        if not awb_code:

            raise ValueError(
                "AWB not returned by Shiprocket: "
                f"{response_data}"
            )

        with transaction.atomic():

            shipment = (
                ShiprocketShipment.objects.select_for_update()
                .get(pk=shipment.pk)
            )

            shipment.awb_code = str(awb_code)

            shipment.courier_name = courier_name

            shipment.tracking_url = tracking_url

            shipment.status = "PICKUP_PENDING"

            shipment.response_data = response_data

            shipment.error_message = ""

            shipment.save()

        logger.info(
            "AWB assigned successfully for order %s: %s",
            order.order_number,
            awb_code,
        )

        return True

    except Exception as exc:

        logger.exception(
            "AWB assignment failed for order %s.",
            order.order_number,
        )

        shipment.error_message = str(exc)

        shipment.response_data = {
            "error": str(exc),
        }

        shipment.save(
            update_fields=[
                "error_message",
                "response_data",
                "updated_at",
            ]
        )

        return False


# ==========================================================
# 9. CANCEL SHIPROCKET ORDER
# ==========================================================

def cancel_shiprocket_order(order):

    """
    Cancel an existing Shiprocket order.

    Returns:
        True  - Cancellation accepted by Shiprocket.
        False - Cancellation failed.
    """

    shipment = ShiprocketShipment.objects.filter(
        order=order
    ).first()

    # No Shiprocket order exists.
    if not shipment or not shipment.shiprocket_order_id:
        return True

    # Already cancelled locally.
    if shipment.status == "CANCELLED":
        return True

    try:

        response_data = shiprocket_request(
            "POST",
            "orders/cancel",
            json={
                "ids": [
                    int(shipment.shiprocket_order_id)
                ]
            },
        )

        # A successful 204 response returns an empty dictionary.
        # The successful HTTP response itself confirms acceptance.

        with transaction.atomic():

            shipment = (
                ShiprocketShipment.objects.select_for_update()
                .get(pk=shipment.pk)
            )

            shipment.status = "CANCELLED"

            shipment.response_data = {
                "cancellation_response": response_data
            }

            shipment.error_message = ""

            shipment.save()

        logger.info(
            "Shiprocket order cancelled: %s",
            order.order_number,
        )

        return True

    except Exception as exc:

        logger.exception(
            "Shiprocket cancellation failed for %s",
            order.order_number,
        )

        shipment.error_message = str(exc)

        shipment.save(
            update_fields=[
                "error_message",
                "updated_at",
            ]
        )

        return False
