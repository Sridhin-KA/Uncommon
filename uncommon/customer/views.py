from django.shortcuts import render, get_object_or_404,redirect
from django.db.models import Q
from .models import *
from admin_panel.models import *
from django.contrib.auth.hashers import make_password
from django.contrib import messages
from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from decimal import Decimal
from django.http import JsonResponse,Http404
import uuid

from django.db import transaction
from django.db.models import F
import json
import uuid
from decimal import Decimal, ROUND_HALF_UP

import razorpay

from django.conf import settings
from django.http import JsonResponse, HttpResponseBadRequest
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db import transaction
from django.db.models import F
import logging
import uuid

from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from django.db import transaction
from django.urls import reverse

logger = logging.getLogger(__name__)
# Create your views here.

def get_logged_in_customer(request):
    customer_id = request.session.get("customer_id")

    if not customer_id:
        return None

    return Customer.objects.filter(id=customer_id).first()

def customer_register(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        phone = request.POST.get('phone', '').strip()
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        print(f"Received registration data: name={name}, email={email}, phone={phone}, username={username}, password={'*' * len(password)}")  # Debugging line

        # Validate required fields
        if not all([name, email, phone, username, password]):
            return render(request, 'admin_panel/auth_page.html', {
                'error': 'Please fill in all fields.',
                'name': name,
                'email': email,
                'phone': phone,
                'username': username,
            })

        # Check email
        if Customer.objects.filter(email__iexact=email).exists():
            return render(request, 'admin_panel/auth_page.html', {
                'error': 'An account with this email already exists.',
                'name': name,
                'email': email,
                'phone': phone,
                'username': username,
            })

        # Check username
        if Customer.objects.filter(username__iexact=username).exists():
            return render(request, 'admin_panel/auth_page.html', {
                'error': 'This username is already taken.',
                'name': name,
                'email': email,
                'phone': phone,
                'username': username,
            })

        # Validate password
        if len(password) < 8:
            return render(request, 'admin_panel/auth_page.html', {
                'error': 'Password must contain at least 8 characters.',
                'name': name,
                'email': email,
                'phone': phone,
                'username': username,
            })

        

        # Create customer with a hashed password
        Customer.objects.create(
            name=name,
            email=email,
            phone=phone,
            username=username,
            password=password,
        )

        messages.success(
            request,
            'Your account has been created. Please sign in.'
        )

        return redirect('login')

    return render(request, 'admin_panel/auth_page.html')

def customer_home(request):
    products = Product.objects.filter(
        stock__gt=0
    ).select_related('category').order_by('-created_at')

    context = {
        'customer': None,
        'featured_products': products[:6],
        'him_count': Product.objects.filter(
            category__section='HIM', stock__gt=0
        ).count(),
        'her_count': Product.objects.filter(
            category__section='HER', stock__gt=0
        ).count(),
        'rare_count': Product.objects.filter(
            Q(is_rare=True) | Q(is_limited=True),
            stock__gt=0
        ).count(),
    }

    customer_id = request.session.get('customer_id')

    if customer_id:
        context['customer'] = Customer.objects.filter(
            id=customer_id
        ).first()
    print("SESSION:", request.session.session_key)
    print("CUSTOMER ID:", request.session.get("customer_id"))
    print("CUSTOMER:", context["customer"])
    return render(request, 'customer/home.html', context)


def section_products(request, section):
    section = section.upper()

    if section not in ("HIM", "HER", "RARE"):
        raise Http404("Section not found")

    products = (
        Product.objects
        .select_related("category")
        .filter(stock__gt=0)
    )

    if section == "RARE":
        products = products.filter(
            Q(is_rare=True) | Q(is_limited=True)
        )
        title = "The Hundred"
        subtitle = "Rare objects. Limited numbers. Never ordinary."

        # Only confirmed orders count as purchases.
        purchased_rare_items = (
            OrderItem.objects
            .filter(order__status="CONFIRMED")
            .filter(
                Q(product__is_rare=True)
                | Q(product__is_limited=True)
            )
            .select_related("order", "product")
            .order_by("order__created_at", "pk")
        )
    else:
        products = products.filter(category__section=section)
        title = "Him" if section == "HIM" else "Her"
        subtitle = (
            "Objects selected for him."
            if section == "HIM"
            else "A different kind of uncommon."
        )
        purchased_rare_items = []

    search = request.GET.get("search", "").strip()

    if search:
        products = products.filter(
            Q(product_name__icontains=search)
            | Q(description__icontains=search)
            | Q(category__category_name__icontains=search)
        )

    products = products.order_by("-created_at")

    return render(
        request,
        "customer/section_products.html",
        {
            "section": section,
            "title": title,
            "subtitle": subtitle,
            "products": products,
            "search": search,
            "purchased_rare_items": purchased_rare_items,
        },
    )

    
@require_POST
def upcoming_reservation(request):
    name = request.POST.get("name", "").strip()
    email = request.POST.get("email", "").strip()
    interest = request.POST.get("interest", "").strip()
    note = request.POST.get("note", "").strip()

    allowed_interests = [
        "The Hundred — next rare release",
        "Limited-edition product",
        "New product launch",
        "Any upcoming release",
    ]

    if (
        not name
        or len(name) > 120
        or len(email) > 254
        or not email
        or interest not in allowed_interests
        or len(note) > 1000
    ):
        messages.error(
            request,
            "Please check your details and try again."
        )
        return redirect(reverse("customer_home") + "#hundred")

    reservation = UpcomingReservation.objects.create(
        name=name,
        email=email,
        interest=interest,
        note=note,
    )

    subject = "Your reservation request | The Hundred — UNCOMMON"

    body = f"""
Hello {reservation.name},

Thank you for your interest in The Hundred by UNCOMMON.

Your reservation request has been received.

Reference: UH-{reservation.pk:06d}
Interest: {reservation.interest}
Date: {reservation.created_at:%d %B %Y}

This email confirms receipt of your request only.
It does not guarantee product availability or confirm a purchase.

Our team will contact you when we have an update.

Made once. Numbered to you.
UNCOMMON — The House
"""

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[reservation.email],
            fail_silently=False,
        )
        messages.success(
            request,
            "Reservation request received! A confirmation email has been sent."
        )
    except Exception:
        messages.warning(
            request,
            "Your request was saved, but the email could not be sent. "
            "Please try again later or contact us."
        )

    return redirect(reverse("customer_home") + "#hundred")

def get_bag(request):
    """Return the cart stored in the current session."""
    return request.session.get("bag", {})



@require_POST
def add_to_bag(request, product_id):
    product = get_object_or_404(Product, id=product_id)

    bag = request.session.get("bag", {})
    key = str(product.id)

    try:
        current_quantity = int(bag.get(key, 0))
    except (ValueError, TypeError):
        current_quantity = 0

    if product.stock < 1:
        return JsonResponse({
            "success": False,
            "message": "This product is out of stock.",
        }, status=400)

    if current_quantity >= product.stock:
        return JsonResponse({
            "success": False,
            "message": "You have added all available stock.",
        }, status=400)

    bag[key] = current_quantity + 1
    request.session["bag"] = bag
    request.session.modified = True

    return JsonResponse({
        "success": True,
        "message": f"{product.product_name} added to your bag.",
        "bag_count": sum(int(qty) for qty in bag.values()),
    })


def bag_view(request):
    customer = get_logged_in_customer(request)

    bag = request.session.get("bag", {})
    items = []
    total = Decimal("0.00")
    bag_count = 0
    cleaned_bag = {}

    for product_id, quantity in bag.items():
        try:
            product = Product.objects.select_related("category").get(
                id=int(product_id)
            )
            quantity = int(quantity)
        except (Product.DoesNotExist, ValueError, TypeError):
            continue

        if quantity < 1 or product.stock < 1:
            continue

        quantity = min(quantity, product.stock)

        line_total = product.price * quantity
        total += line_total
        bag_count += quantity

        cleaned_bag[str(product.id)] = quantity

        items.append({
            "product": product,
            "quantity": quantity,
            "line_total": line_total,
        })

    if cleaned_bag != bag:
        request.session["bag"] = cleaned_bag
        request.session.modified = True

    return render(request, "customer/bag.html", {
        "customer": customer,
        "items": items,
        "total": total,
        "bag_count": bag_count,
    })

@require_POST
def update_bag_quantity(request, product_id):
    

    bag = request.session.get("bag", {})
    product = get_object_or_404(Product, id=product_id)
    key = str(product.id)

    if key not in bag:
        messages.error(request, "This product is not in your bag.")
        return redirect("bag_view")

    try:
        quantity = int(bag[key])
    except (ValueError, TypeError):
        quantity = 1

    action = request.POST.get("action")

    if action == "increase":
        if product.stock < 1:
            bag.pop(key, None)
            messages.error(request, "This product is out of stock.")
        elif quantity < product.stock:
            bag[key] = quantity + 1
            messages.success(request, "Bag quantity updated.")
        else:
            messages.error(
                request,
                f"Only {product.stock} item(s) are available."
            )

    elif action == "decrease":
        if quantity > 1:
            bag[key] = quantity - 1
            messages.success(request, "Bag quantity updated.")
        else:
            messages.info(
                request,
                "The minimum quantity is 1. Remove the item if you don't want it."
            )
    else:
        messages.error(request, "Invalid quantity action.")

    request.session["bag"] = bag
    request.session.modified = True

    return redirect("bag_view")

@require_POST
def remove_from_bag(request, product_id):
    

    bag = request.session.get("bag", {})
    key = str(product_id)

    if key in bag:
        bag.pop(key)
        request.session["bag"] = bag
        request.session.modified = True
        messages.success(request, "Product removed from your bag.")
    else:
        messages.error(request, "This product is not in your bag.")

    return redirect("bag_view")



from decimal import Decimal, ROUND_HALF_UP
import uuid

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render


def checkout(request):
    customer = get_logged_in_customer(request)

    if not customer:
        request.session["next_after_login"] = "checkout"
        request.session.modified = True
        messages.info(request, "Please log in before checkout.")
        return redirect("login")

    bag = request.session.get("bag", {})

    if not bag:
        messages.info(request, "Your bag is empty.")
        return redirect("bag_view")

    addresses = CustomerAddress.objects.filter(
        customer=customer
    ).order_by("-is_default", "-created_at")

    default_address = addresses.filter(is_default=True).first()

    if default_address is None:
        default_address = addresses.first()

    selected_address_id = (
        str(default_address.id) if default_address else ""
    )

    # -----------------------------------------------
    # BUILD BAG ITEMS
    # -----------------------------------------------
    items = []
    total = Decimal("0.00")

    for product_id, quantity in bag.items():
        try:
            product = Product.objects.get(id=int(product_id))
            quantity = int(quantity)
        except (Product.DoesNotExist, ValueError, TypeError):
            continue

        if quantity < 1:
            continue

        if quantity > product.stock:
            messages.error(
                request,
                f"Only {product.stock} of "
                f"{product.product_name} are available."
            )
            return redirect("bag_view")

        line_total = product.price * quantity
        total += line_total

        items.append({
            "product": product,
            "quantity": quantity,
            "line_total": line_total,
        })

    if not items:
        request.session["bag"] = {}
        request.session.modified = True

        messages.error(
            request,
            "Your bag contains no available products."
        )
        return redirect("bag_view")

    # -----------------------------------------------
    # INITIAL CHECKOUT TOTALS FOR THE TEMPLATE
    # -----------------------------------------------
    processing_fee = (
        total * Decimal("0.10")
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    shipping_fee = Decimal("0.00")
    grand_total = total + processing_fee + shipping_fee

    # -----------------------------------------------
    # HANDLE CHECKOUT SUBMISSION
    # -----------------------------------------------
    if request.method == "POST":
        address_action = request.POST.get(
            "address_action", "select"
        )

        # -------------------------------------------
        # OPTION 1: USE A SAVED ADDRESS
        # -------------------------------------------
        if address_action == "select":
            selected_address_id = request.POST.get(
                "address_id", ""
            ).strip()

            if not selected_address_id:
                messages.error(
                    request,
                    "Please select a delivery address."
                )
                return render(request, "customer/checkout.html", {
                    "customer": customer,
                    "items": items,
                    "total": total,
                    "processing_fee": processing_fee,
                    "shipping_fee": shipping_fee,
                    "grand_total": grand_total,
                    "addresses": addresses,
                    "selected_address_id": selected_address_id,
                })

            selected_address = get_object_or_404(
                CustomerAddress,
                id=selected_address_id,
                customer=customer,
            )

        # -------------------------------------------
        # OPTION 2: ADD AND USE A NEW ADDRESS
        # -------------------------------------------
        elif address_action == "new":
            name = request.POST.get("name", "").strip()
            phone = request.POST.get("phone", "").strip()
            address_line = request.POST.get(
                "address_line", ""
            ).strip()
            city = request.POST.get("city", "").strip()
            state = request.POST.get("state", "").strip()
            pincode = request.POST.get("pincode", "").strip()

            required_fields = {
                "Name": name,
                "Phone": phone,
                "Address": address_line,
                "City": city,
                "State": state,
                "PIN code": pincode,
            }

            missing_fields = [
                field
                for field, value in required_fields.items()
                if not value
            ]

            if missing_fields:
                messages.error(
                    request,
                    "Please fill in: " + ", ".join(missing_fields)
                )
                return render(request, "customer/checkout.html", {
                    "customer": customer,
                    "items": items,
                    "total": total,
                    "processing_fee": processing_fee,
                    "shipping_fee": shipping_fee,
                    "grand_total": grand_total,
                    "addresses": addresses,
                    "selected_address_id": "",
                    "new_address_data": request.POST,
                    "show_new_address": True,
                })

            new_address = CustomerAddress(
                customer=customer,
                name=name,
                phone=phone,
                address_line=address_line,
                city=city,
                state=state,
                pincode=pincode,
                is_default=not addresses.exists(),
            )

            try:
                new_address.full_clean()
                new_address.save()

            except ValidationError as exc:
                for field_errors in exc.message_dict.values():
                    for error in field_errors:
                        messages.error(request, error)

                return render(request, "customer/checkout.html", {
                    "customer": customer,
                    "items": items,
                    "total": total,
                    "processing_fee": processing_fee,
                    "shipping_fee": shipping_fee,
                    "grand_total": grand_total,
                    "addresses": addresses,
                    "selected_address_id": "",
                    "new_address_data": request.POST,
                    "show_new_address": True,
                })

            selected_address = new_address

        else:
            messages.error(request, "Invalid address selection.")
            return redirect("checkout")

        # Store an address snapshot with the order.
        shipping_address = (
            f"{selected_address.name}\n"
            f"{selected_address.phone}\n"
            f"{selected_address.address_line}\n"
            f"{selected_address.city}, {selected_address.state} "
            f"- {selected_address.pincode}"
        )

        # -----------------------------------------------
        # RECHECK STOCK AND PRICES, THEN CREATE PAYMENT
        # -----------------------------------------------
        # Do NOT reduce stock or clear the bag before payment succeeds.
        order = None

        try:
            with transaction.atomic():
                product_ids = sorted(
                    item["product"].id for item in items
                )

                locked_products = {
                    product.id: product
                    for product in Product.objects.select_for_update()
                    .filter(id__in=product_ids)
                    .order_by("id")
                }

                verified_items = []
                verified_total = Decimal("0.00")

                for item in items:
                    product = locked_products.get(item["product"].id)
                    quantity = item["quantity"]

                    if not product or product.stock < quantity:
                        messages.error(
                            request,
                            f"Insufficient stock for "
                            f"{item['product'].product_name}.",
                        )
                        return redirect("bag_view")

                    verified_items.append((product, quantity))
                    verified_total += product.price * quantity

                verified_total = verified_total.quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )

                verified_processing_fee = (
                    verified_total * Decimal("0.10")
                ).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )

                verified_shipping_fee = Decimal("0.00")
                verified_grand_total = (
                    verified_total
                    + verified_processing_fee
                    + verified_shipping_fee
                )

                order = Order.objects.create(
                    customer=customer,
                    order_number=f"INS-{uuid.uuid4().hex[:12].upper()}",
                    total_amount=verified_grand_total,
                    shipping_address=shipping_address,
                    status="PENDING",
                )

                OrderItem.objects.bulk_create([
                    OrderItem(
                        order=order,
                        product=product,
                        quantity=quantity,
                        price=product.price,
                    )
                    for product, quantity in verified_items
                ])

            # Razorpay expects the amount in paise (₹1 = 100 paise).
            amount_paise = int(verified_grand_total * 100)
            client = get_razorpay_client()

            razorpay_order = client.order.create({
                "amount": amount_paise,
                "currency": "INR",
                "receipt": order.order_number,
                "notes": {"order_number": order.order_number},
            })

            payment = Payment.objects.create(
                order=order,
                razorpay_order_id=razorpay_order["id"],
                amount=verified_grand_total,
                currency="INR",
                status="CREATED",
            )

        except Exception:
            # Keep internal details in server logs, never show secrets to users.
            logger.exception("Failed to initialize Razorpay checkout")

            if order is not None:
                Order.objects.filter(
                    pk=order.pk,
                    status="PENDING",
                ).update(status="CANCELLED")

            messages.error(
                request,
                "We couldn't start the payment. Please try again.",
            )
            return redirect("checkout")

        # Data consumed by the Razorpay JavaScript in checkout.html.
        razorpay_data = {
            "key": settings.RAZORPAY_KEY_ID,
            "amount": amount_paise,
            "currency": "INR",
            "order_number": order.order_number,
            "razorpay_order_id": payment.razorpay_order_id,
            "verify_url": reverse("verify_razorpay_payment"),
            "customer_name": (
                getattr(customer, "name", "")
                or getattr(customer, "username", "")
            ),
            "customer_email": getattr(customer, "email", ""),
            "customer_phone": getattr(customer, "phone", ""),
        }

        return render(request, "customer/checkout.html", {
            "customer": customer,
            "items": items,
            "total": verified_total,
            "processing_fee": verified_processing_fee,
            "shipping_fee": verified_shipping_fee,
            "grand_total": verified_grand_total,
            "addresses": addresses,
            "selected_address_id": str(selected_address.id),
            "razorpay_data": razorpay_data,
        })

    # -----------------------------------------------
    # DISPLAY CHECKOUT PAGE
    # -----------------------------------------------
    return render(request, "customer/checkout.html", {
        "customer": customer,
        "items": items,
        "total": total,
        "processing_fee": processing_fee,
        "shipping_fee": shipping_fee,
        "grand_total": grand_total,
        "addresses": addresses,
        "selected_address_id": selected_address_id,
    })
def order_success(request, order_number):
    customer = get_logged_in_customer(request)

    if not customer:
        messages.info(request, "Please log in to view your order.")
        return redirect("login")

    order = get_object_or_404(
        Order.objects.prefetch_related("items__product"),
        order_number=order_number,
        customer=customer,
    )

    return render(request, "customer/order_success.html", {
        "order": order,
    })


def finalize_captured_payment(payment_record, razorpay_payment_id):
    """
    Call only after verifying the payment signature and confirming
    Razorpay reports the payment as captured for the expected amount.
    """
    with transaction.atomic():
        payment = (
            Payment.objects.select_for_update()
            .select_related("order")
            .get(pk=payment_record.pk)
        )
        order = Order.objects.select_for_update().get(
            pk=payment.order_id
        )

        if order.status == "CONFIRMED":
            return True, "Payment already confirmed."

        order_items = list(
            OrderItem.objects.filter(order=order).order_by("product_id")
        )
        product_ids = sorted({item.product_id for item in order_items})

        locked_products = {
            product.id: product
            for product in Product.objects.select_for_update()
            .filter(id__in=product_ids)
            .order_by("id")
        }

        # A captured payment cannot be treated as unpaid just because
        # inventory changed. Record the payment and flag the order.
        insufficient = []
        for item in order_items:
            product = locked_products.get(item.product_id)
            if not product or product.stock < item.quantity:
                insufficient.append(
                    getattr(product, "product_name", str(item.product_id))
                )

        payment.razorpay_payment_id = razorpay_payment_id
        payment.status = "PAID"
        payment.save(update_fields=[
            "razorpay_payment_id",
            "status",
            "updated_at",
        ])

        if insufficient:
            # Payment was captured, but the order cannot be fulfilled.
            # This needs a refund/manual support workflow.
            return False, (
                "Payment was captured, but stock is insufficient for: "
                + ", ".join(insufficient)
            )

        # Deduct stock once, while product rows are locked.
        for item in order_items:
            Product.objects.filter(pk=item.product_id).update(
                stock=F("stock") - item.quantity
            )

        order.status = "CONFIRMED"
        order.save(update_fields=["status", "updated_at"])

        return True, "Payment confirmed."


@require_POST
def verify_razorpay_payment(request):
    customer = get_logged_in_customer(request)
    if not customer:
        return JsonResponse(
            {"success": False, "error": "Please log in again."},
            status=401,
        )

    try:
        data = json.loads(request.body)
        order_number = data["order_number"]
        razorpay_order_id = data["razorpay_order_id"]
        razorpay_payment_id = data["razorpay_payment_id"]
        razorpay_signature = data["razorpay_signature"]
    except (ValueError, KeyError, TypeError):
        return JsonResponse(
            {"success": False, "error": "Invalid payment response."},
            status=400,
        )

    try:
        payment = Payment.objects.select_related("order").get(
            order__order_number=order_number,
            order__customer=customer,
            razorpay_order_id=razorpay_order_id,
        )
    except Payment.DoesNotExist:
        return JsonResponse(
            {"success": False, "error": "Payment record not found."},
            status=404,
        )

    try:
        client = get_razorpay_client()
        client.utility.verify_payment_signature({
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": razorpay_signature,
        })

        # Signature alone is not enough: check the payment with Razorpay.
        remote_payment = client.payment.fetch(razorpay_payment_id)

        expected_amount = int(payment.amount * 100)

        if (
            remote_payment.get("order_id") != payment.razorpay_order_id
            or int(remote_payment.get("amount", -1)) != expected_amount
            or remote_payment.get("currency") != payment.currency
        ):
            return JsonResponse(
                {"success": False, "error": "Payment details do not match."},
                status=400,
            )

        if remote_payment.get("status") != "captured":
            payment.status = "PENDING"
            payment.save(update_fields=["status", "updated_at"])
            return JsonResponse(
                {
                    "success": False,
                    "error": (
                        "Payment is not captured yet. Please wait before "
                        "retrying or contact support if money was deducted."
                    ),
                },
                status=409,
            )

        success, message = finalize_captured_payment(
            payment,
            razorpay_payment_id,
        )

        if not success:
            return JsonResponse(
                {"success": False, "error": message},
                status=409,
            )

        # Clear the bag only after successful verification and fulfilment.
        request.session["bag"] = {}
        request.session.modified = True

        return JsonResponse({
            "success": True,
            "redirect_url": reverse(
                "order_success",
                kwargs={"order_number": payment.order.order_number},
            ),
        })

    except razorpay.errors.SignatureVerificationError:
        return JsonResponse(
            {"success": False, "error": "Payment signature verification failed."},
            status=400,
        )
    except Exception:
        # Log exception details server-side; never return secrets to the client.
        return JsonResponse(
            {
                "success": False,
                "error": (
                    "We couldn't confirm the payment status. Do not pay again "
                    "immediately; contact support if money was deducted."
                ),
            },
            status=502,
        )


@csrf_exempt
@require_POST
def razorpay_webhook(request):
    """
    Configure this endpoint in the Razorpay Dashboard.
    Use the webhook secret, which is separate from the API key secret.
    """
    signature = request.headers.get("X-Razorpay-Signature", "")
    webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET

    if not signature or not webhook_secret:
        return HttpResponseBadRequest("Missing webhook signature or secret.")

    try:
        client = get_razorpay_client()
        client.utility.verify_webhook_signature(
            request.body.decode("utf-8"),
            signature,
            webhook_secret,
        )
        event_data = json.loads(request.body)
    except Exception:
        return HttpResponseBadRequest("Invalid webhook.")

    event = event_data.get("event")
    entity = (
        event_data.get("payload", {})
        .get("payment", {})
        .get("entity", {})
    )

    if event not in ("payment.captured", "payment.failed"):
        return JsonResponse({"received": True})

    razorpay_order_id = entity.get("order_id")
    razorpay_payment_id = entity.get("id")

    if not razorpay_order_id:
        return JsonResponse({"received": True})

    try:
        payment = Payment.objects.select_related("order").get(
            razorpay_order_id=razorpay_order_id
        )
    except Payment.DoesNotExist:
        # Unknown orders can be retried after the local record is available.
        return JsonResponse({"received": False}, status=404)

    if event == "payment.failed":
        if payment.status != "PAID":
            payment.status = "FAILED"
            payment.save(update_fields=["status", "updated_at"])
        return JsonResponse({"received": True})

    # For payment.captured, validate amount/currency before fulfilment.
    expected_amount = int(payment.amount * 100)
    if (
        entity.get("status") != "captured"
        or int(entity.get("amount", -1)) != expected_amount
        or entity.get("currency") != payment.currency
        or not razorpay_payment_id
    ):
        return HttpResponseBadRequest("Captured payment details do not match.")

    finalize_captured_payment(payment, razorpay_payment_id)
    return JsonResponse({"received": True})


def get_razorpay_client():
    key_id = settings.RAZORPAY_KEY_ID
    key_secret = settings.RAZORPAY_KEY_SECRET

    if not key_id or not key_secret:
        raise RuntimeError("Razorpay credentials are not configured.")

    return razorpay.Client(auth=(key_id, key_secret))


def my_orders(request):
    customer = get_logged_in_customer(request)

    if not customer:
        return redirect("login")

    orders = (
        Order.objects
        .filter(customer=customer)
        .prefetch_related("items__product")
        .order_by("-created_at")
    )

    return render(request, "customer/my_orders.html", {
        "customer": customer,
        "orders": orders,
    })


def order_detail(request, order_number):
    customer = get_logged_in_customer(request)

    if not customer:
        return redirect("login")

    order = get_object_or_404(
        Order.objects.prefetch_related("items__product"),
        order_number=order_number,
        customer=customer,
    )

    return render(request, "customer/order_detail.html", {
        "customer": customer,
        "order": order,
    })


@require_POST
def cancel_order(request, order_number):
    customer = get_logged_in_customer(request)

    if not customer:
        return redirect("login")

    with transaction.atomic():
        order = get_object_or_404(
            Order.objects.select_for_update(),
            order_number=order_number,
            customer=customer,
        )

        if order.status not in ["PENDING", "CONFIRMED"]:
            messages.error(
                request,
                "This order can no longer be cancelled."
            )
            return redirect("order_detail", order_number=order.order_number)

        # Restore stock for each item in the cancelled order.
        for item in order.items.all():
            Product.objects.filter(pk=item.product_id).update(
                stock=F("stock") + item.quantity
            )

        order.status = "CANCELLED"
        order.save(update_fields=["status", "updated_at"])

    messages.success(request, "Your order has been cancelled.")

    return redirect("order_detail", order_number=order_number)



@require_POST
def cancel_order(request, order_number):
    customer = get_logged_in_customer(request)

    if not customer:
        return redirect("login")

    with transaction.atomic():
        order = get_object_or_404(
            Order.objects.select_for_update(),
            order_number=order_number,
            customer=customer,
        )

        # Only pending orders can be cancelled.
        if order.status != "PENDING":
            messages.error(
                request,
                "Only pending orders can be cancelled."
            )
            return redirect(
                "order_detail",
                order_number=order.order_number
            )

        # Restore the stock reduced during checkout.
        for item in order.items.all():
            Product.objects.filter(pk=item.product_id).update(
                stock=F("stock") + item.quantity
            )

        order.status = "CANCELLED"
        order.save(update_fields=["status", "updated_at"])

    messages.success(request, "Your order has been cancelled successfully.")
    return redirect("my_orders")



def wishlist_view(request):
    customer = get_logged_in_customer(request)

    if customer:
        wishlist_products = Product.objects.filter(
            wishlisted_by__customer=customer
        ).select_related('category').order_by(
            '-wishlisted_by__created_at'
        )
    else:
        wishlist_ids = request.session.get('wishlist', [])
        wishlist_products = Product.objects.filter(
            id__in=wishlist_ids
        ).select_related('category')

        # Preserve the guest's selected order
        product_map = {
            product.id: product for product in wishlist_products
        }
        wishlist_products = [
            product_map[int(product_id)]
            for product_id in wishlist_ids
            if str(product_id).isdigit()
            and int(product_id) in product_map
        ]

    return render(request, 'customer/wishlist.html', {
        'customer': customer,
        'wishlist_products': wishlist_products,
        'wishlist_count': len(wishlist_products),
    })


@require_POST
def add_to_wishlist(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    customer = get_logged_in_customer(request)

    if customer:
        Wishlist.objects.get_or_create(
            customer=customer,
            product=product,
        )
    else:
        wishlist = request.session.get('wishlist', [])
        wishlist = [str(pid) for pid in wishlist]

        if str(product.id) not in wishlist:
            wishlist.append(str(product.id))

        request.session['wishlist'] = wishlist
        request.session.modified = True

    messages.success(request, 'Product added to your wishlist.')
    return redirect('wishlist_view')


@require_POST
def remove_from_wishlist(request, product_id):
    customer = get_logged_in_customer(request)

    if customer:
        Wishlist.objects.filter(
            customer=customer,
            product_id=product_id,
        ).delete()
    else:
        wishlist = request.session.get('wishlist', [])
        request.session['wishlist'] = [
            str(pid) for pid in wishlist
            if str(pid) != str(product_id)
        ]
        request.session.modified = True

    messages.success(request, 'Product removed from your wishlist.')
    return redirect('wishlist_view')


@require_POST
def move_to_bag(request, product_id):
    product = get_object_or_404(Product, id=product_id)

    if product.stock < 1:
        messages.error(request, 'This product is currently out of stock.')
        return redirect('wishlist_view')

    bag = request.session.get('bag', {})
    bag = {
        str(pid): int(quantity)
        for pid, quantity in bag.items()
        if str(pid).isdigit()
        and str(quantity).isdigit()
        and int(quantity) > 0
    }

    product_key = str(product.id)
    current_quantity = bag.get(product_key, 0)

    if current_quantity >= product.stock:
        messages.error(
            request,
            f'You already have the maximum available quantity of '
            f'{product.product_name} in your bag.'
        )
        return redirect('wishlist_view')

    bag[product_key] = current_quantity + 1
    request.session['bag'] = bag
    request.session.modified = True

    customer = get_logged_in_customer(request)

    if customer:
        Wishlist.objects.filter(
            customer=customer,
            product=product,
        ).delete()
    else:
        wishlist = request.session.get('wishlist', [])
        request.session['wishlist'] = [
            str(pid) for pid in wishlist
            if str(pid) != str(product.id)
        ]

    messages.success(request, 'Product moved to your bag.')
    return redirect('bag_view')


def get_profile_customer(request):
    customer_id = request.session.get("customer_id")

    if not customer_id:
        return None

    return Customer.objects.filter(id=customer_id).first()


def customer_profile(request):
    customer = get_profile_customer(request)

    if not customer:
        messages.info(request, "Please sign in to view your profile.")
        return redirect("login")

    orders = Order.objects.filter(
        customer=customer
    ).order_by("-created_at")

    # Get the customer's saved address
    customer_address = CustomerAddress.objects.filter(
        customer=customer
    ).order_by("-is_default", "-created_at").first()

    return render(request, "customer/profile.html", {
        "customer": customer,
        "orders": orders,
        "total_orders": orders.count(),
        "delivered_orders": orders.filter(status="DELIVERED").count(),
        "customer_address": customer_address,
    })
    
    
def edit_customer_profile(request):
    customer = get_profile_customer(request)

    if not customer:
        messages.info(request, "Please sign in to edit your profile.")
        return redirect("login")

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip().lower()
        username = request.POST.get("username", "").strip()
        phone = request.POST.get("phone", "").strip()

        if not all([name, email, username, phone]):
            messages.error(request, "Please fill in all fields.")
        elif Customer.objects.filter(
            email__iexact=email
        ).exclude(pk=customer.pk).exists():
            messages.error(request, "That email is already registered.")
        elif Customer.objects.filter(
            username__iexact=username
        ).exclude(pk=customer.pk).exists():
            messages.error(request, "That username is already taken.")
        else:
            customer.name = name
            customer.email = email
            customer.username = username
            customer.phone = phone
            customer.save()

            messages.success(request, "Your profile has been updated.")
            return redirect("customer_profile")

    return render(request, "customer/edit_profile.html", {
        "customer": customer,
    })
    
def manage_address(request):
    """
    The address editor is embedded in profile.html,
    so send customers to their profile instead of a separate page.
    """
    return redirect("customer_profile")


@require_POST
def save_address(request):
    customer_id = request.session.get("customer_id")

    if not customer_id:
        messages.error(request, "Please log in first.")
        return redirect("login")

    customer = get_object_or_404(Customer, id=customer_id)

    name = request.POST.get("name", "").strip()
    phone = request.POST.get("phone", "").strip()
    address_line = request.POST.get("address_line", "").strip()
    city = request.POST.get("city", "").strip()
    state = request.POST.get("state", "").strip()
    pincode = request.POST.get("pincode", "").strip()

    # Validate required fields.
    if not all([name, phone, address_line, city, state, pincode]):
        messages.error(request, "Please fill in all address fields.")
        return redirect("customer_profile")

    # Validate Indian PIN code.
    if not pincode.isdigit() or len(pincode) != 6:
        messages.error(request, "Enter a valid 6-digit PIN code.")
        return redirect("customer_profile")

    # Allow digits and common phone-number symbols.
    phone_digits = "".join(char for char in phone if char.isdigit())

    if (
        len(phone_digits) < 10
        or len(phone_digits) > 15
        or any(char not in "0123456789+()- " for char in phone)
    ):
        messages.error(request, "Enter a valid phone number.")
        return redirect("customer_profile")

    with transaction.atomic():
        # Update the customer's existing default address first.
        address = (
            CustomerAddress.objects
            .filter(customer=customer, is_default=True)
            .first()
        )

        # If no default exists, update their first saved address.
        if address is None:
            address = (
                CustomerAddress.objects
                .filter(customer=customer)
                .order_by("-created_at")
                .first()
            )

        # Create the first address if none has been saved.
        if address is None:
            address = CustomerAddress(customer=customer)

        # Keep one default address for this customer.
        CustomerAddress.objects.filter(
            customer=customer,
            is_default=True
        ).exclude(pk=address.pk).update(is_default=False)

        address.name = name
        address.phone = phone
        address.address_line = address_line
        address.city = city
        address.state = state
        address.pincode = pincode
        address.is_default = True
        address.save()

    messages.success(request, "Delivery address saved successfully.")
    return redirect("customer_profile")


@require_POST
def delete_address(request, address_id):
    customer_id = request.session.get("customer_id")

    if not customer_id:
        messages.error(request, "Please log in first.")
        return redirect("login")

    customer = get_object_or_404(Customer, id=customer_id)

    address = get_object_or_404(
        CustomerAddress,
        id=address_id,
        customer=customer
    )

    was_default = address.is_default
    address.delete()

    if was_default:
        next_address = CustomerAddress.objects.filter(
            customer=customer
        ).order_by("-created_at").first()

        if next_address:
            next_address.is_default = True
            next_address.save(update_fields=["is_default"])

    messages.success(request, "Address deleted successfully.")
    return redirect("customer_profile")