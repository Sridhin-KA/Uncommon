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
from django.contrib import messages
from django.db.models import Avg, Count, Q, Prefetch
from django.db.models.functions import Coalesce
from django.db import transaction
from django.db.models import F
import json
import uuid
from decimal import Decimal, ROUND_HALF_UP
import re
import razorpay

from django.conf import settings
from django.http import JsonResponse, HttpResponseBadRequest
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db import transaction
from django.db.models import F
import logging
import hmac
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
    products = (
        Product.objects
        .filter(
            stock__gt=0,
            is_archived=False
        )
        .exclude(
            category__category_name__iexact="Purchase Entries"
        )
        .select_related("category")
        .order_by("-created_at")
    )

    context = {
        "customer": None,
        "featured_products": products[:6],

        "him_count": Product.objects.filter(
            category__section="HIM",
            stock__gt=0,
            is_archived=False
        ).exclude(
            category__category_name__iexact="Purchase Entries"
        ).count(),

        "her_count": Product.objects.filter(
            category__section="HER",
            stock__gt=0,
            is_archived=False
        ).exclude(
            category__category_name__iexact="Purchase Entries"
        ).count(),

        "rare_count": Product.objects.filter(
            Q(is_rare=True) | Q(is_limited=True),
            stock__gt=0,
            is_archived=False
        ).exclude(
            category__category_name__iexact="Purchase Entries"
        ).count(),
    }

    customer_id = request.session.get("customer_id")

    if customer_id:
        context["customer"] = Customer.objects.filter(
            id=customer_id
        ).first()

    print("SESSION:", request.session.session_key)
    print("CUSTOMER ID:", request.session.get("customer_id"))
    print("CUSTOMER:", context["customer"])

    return render(request, "customer/home.html", context)


def section_products(request, section):
    section = section.upper()

    if section not in ("HIM", "HER", "RARE"):
        raise Http404("Section not found")

    # Logged-in customer
    customer = None
    customer_id = request.session.get("customer_id")

    if customer_id:
        customer = Customer.objects.filter(
            pk=customer_id
        ).first()

    # Feedback queryset
    feedback_queryset = (
        Feedback.objects
        .select_related("customer")
        .order_by("-created_at")
    )

    # Base product queryset
    products_queryset = (
        Product.objects
        .select_related("category")
        .prefetch_related(
            Prefetch(
                "feedbacks",
                queryset=feedback_queryset,
                to_attr="feedback_list"
            )
        )
        .annotate(
            average_rating=Avg("feedbacks__rating"),
            review_count=Count("feedbacks", distinct=True),
        )
        .filter(
            stock__gt=0,
            is_archived=False
        )
        .exclude(
            category__category_name__iexact="Purchase Entries"
        )
    )

    # Section filtering
    if section == "RARE":

        products_queryset = products_queryset.filter(
            Q(is_rare=True) | Q(is_limited=True)
        )

        title = "The Hundred"
        subtitle = "Rare objects. Limited numbers. Never ordinary."

        purchased_rare_items = (
            OrderItem.objects
            .filter(order__status="CONFIRMED")
            .filter(
                Q(product__is_rare=True)
                | Q(product__is_limited=True)
            )
            .exclude(
                product__category__category_name__iexact="Purchase Entries"
            )
            .exclude(
                product__is_archived=True
            )
            .select_related(
                "order",
                "product",
                "order__customer"
            )
            .order_by("order__created_at", "pk")
        )

        purchase_customer_names = list(
            purchased_rare_items.values_list(
                "order__customer__name",
                flat=True
            ).distinct()
        )

    else:

        products_queryset = products_queryset.filter(
            category__section=section
        )

        title = "Him" if section == "HIM" else "Her"

        subtitle = (
            "Objects selected for him."
            if section == "HIM"
            else "A different kind of uncommon."
        )

        purchased_rare_items = []
        purchase_customer_names = []

    # Search
    search = request.GET.get("search", "").strip()

    if search:
        products_queryset = products_queryset.filter(
            Q(product_name__icontains=search)
            | Q(description__icontains=search)
            | Q(category__category_name__icontains=search)
        )

    # Fetch products
    products = list(
        products_queryset.order_by("-created_at")
    )

    # Delivered orders for logged-in customer
    if customer:

        product_ids = [
            product.pk for product in products
        ]

        delivered_items = (
            OrderItem.objects
            .filter(
                order__customer=customer,
                order__status="DELIVERED",
                product_id__in=product_ids,
            )
            .select_related("order")
            .order_by("-order__created_at")
        )

        existing_feedback = {
            (feedback.product_id, feedback.order_number): feedback
            for feedback in Feedback.objects.filter(
                customer=customer,
                product_id__in=product_ids,
            )
        }

        review_orders_by_product = {}

        for item in delivered_items:

            order_number = item.order.order_number
            key = (item.product_id, order_number)

            review_orders_by_product.setdefault(
                item.product_id, []
            )

            if any(
                row["order_number"] == order_number
                for row in review_orders_by_product[item.product_id]
            ):
                continue

            review_orders_by_product[item.product_id].append({
                "order_number": order_number,
                "feedback": existing_feedback.get(key),
            })

        for product in products:
            product.review_orders = review_orders_by_product.get(
                product.pk, []
            )

    else:

        for product in products:
            product.review_orders = []

    # Rating distribution
    for product in products:

        feedback_list = list(
            getattr(product, "feedback_list", [])
        )

        product.feedback_list = feedback_list
        product.rating_breakdown = []

        for stars in range(5, 0, -1):

            count = sum(
                1 for review in feedback_list
                if review.rating == stars
            )

            total = product.review_count or 0

            product.rating_breakdown.append({
                "stars": stars,
                "count": count,
                "percent": (
                    round((count / total) * 100)
                    if total else 0
                ),
            })

    # Bag count
    bag = request.session.get("bag", {})

    bag_count = (
        sum(int(qty) for qty in bag.values())
        if isinstance(bag, dict)
        else 0
    )

    return render(
        request,
        "customer/section_products.html",
        {
            "section": section,
            "title": title,
            "subtitle": subtitle,
            "products": products,
            "search": search,
            "customer": customer,
            "bag_count": bag_count,
            "purchased_rare_items": purchased_rare_items,
            "purchase_customer_names": purchase_customer_names,
        },
    )

def product_detail(request, product_id):
    product = get_object_or_404(
        Product.objects
        .select_related("category")
        .prefetch_related(
            Prefetch(
                "feedbacks",
                queryset=Feedback.objects.select_related(
                    "customer"
                ).order_by("-created_at"),
                to_attr="feedback_list"
            )
        )
        .annotate(
            average_rating=Avg("feedbacks__rating"),
            review_count=Count("feedbacks", distinct=True),
        ),
        pk=product_id
    )

    # Determine collection
    section = (
        "RARE"
        if product.is_rare or product.is_limited
        else product.category.section
    )

    # Customer
    customer = None
    customer_id = request.session.get("customer_id")

    if customer_id:
        customer = Customer.objects.filter(
            pk=customer_id
        ).first()

    # Rating breakdown
    reviews = product.feedback_list
    product.rating_breakdown = []

    for stars in range(5, 0, -1):
        count = sum(
            1 for review in reviews
            if review.rating == stars
        )

        total = product.review_count or 0

        product.rating_breakdown.append({
            "stars": stars,
            "count": count,
            "percent": round((count / total) * 100)
            if total else 0,
        })

    # Extract colour from existing overview field
    raw_overview = (product.overview or "").strip()

    product_colour = ""
    product_overview = raw_overview

    colour_match = re.match(
        r"^\s*(?:colour|color)\s*:\s*(.*)$",
        raw_overview,
        flags=re.IGNORECASE | re.DOTALL
    )

    if colour_match:
        details = colour_match.group(1).strip()

        # Preferred format:
        # Colour: Smoked Walnut | Crafted from full-grain hide...
        if "|" in details:
            product_colour, product_overview = details.split("|", 1)

        else:
            # Existing format:
            # Colour: Smoked Walnut Crafted from full-grain hide...
            legacy_match = re.match(
                r"^(.*?)\s+(?=crafted\s+from\b)(.*)$",
                details,
                flags=re.IGNORECASE | re.DOTALL
            )

            if legacy_match:
                product_colour = legacy_match.group(1).strip()
                product_overview = legacy_match.group(2).strip()
            else:
                # No description separator found
                product_colour = details
                product_overview = ""

        product_colour = product_colour.strip(" |–—-:")
        product_overview = product_overview.strip()

    # Bag count
    bag = request.session.get("bag", {})

    bag_count = (
        sum(int(qty) for qty in bag.values())
        if isinstance(bag, dict) else 0
    )

    return render(
        request,
        "customer/product_detail.html",
        {
            "product": product,
            "section": section,
            "customer": customer,
            "bag_count": bag_count,
            "product_colour": product_colour,
            "product_overview": product_overview,
        }
    )
@require_POST
def submit_product_feedback(request, product_id):
    """
    Create or update a review for a product.
    A customer can only review a product from an order that is DELIVERED.
    The unique constraint on (customer, product, order_number) prevents
    duplicate reviews for the same purchase.
    """
    customer_id = request.session.get("customer_id")
    if not customer_id:
        request.session["next_after_login"] = "customer_home"
        messages.info(request, "Please sign in to leave a product review.")
        return redirect("login")

    customer = get_object_or_404(Customer, pk=customer_id)
    product = get_object_or_404(
        Product.objects.select_related("category"),
        pk=product_id,
    )

    order_number = request.POST.get("order_number", "").strip()
    comment = request.POST.get("comment", "").strip()

    try:
        rating = int(request.POST.get("rating", ""))
    except (TypeError, ValueError):
        rating = 0

    if not order_number or len(order_number) > 50:
        messages.error(request, "Please select a valid delivered order.")
        return redirect("section_products", product.category.section)

    if rating not in range(1, 6):
        messages.error(request, "Please select a rating from 1 to 5 stars.")
        return redirect("section_products", product.category.section)

    if not comment or len(comment) > 1000:
        messages.error(request, "Your review must contain 1–1000 characters.")
        return redirect("section_products", product.category.section)

    # Server-side ownership and delivery verification. Never trust the
    # order number supplied by the browser on its own.
    purchased_and_delivered = OrderItem.objects.filter(
        order__customer=customer,
        order__order_number=order_number,
        order__status="DELIVERED",
        product=product,
    ).exists()

    if not purchased_and_delivered:
        messages.error(
            request,
            "Only customers with a delivered purchase can review this product.",
        )
        return redirect("section_products", product.category.section)

    feedback, created = Feedback.objects.update_or_create(
        customer=customer,
        product=product,
        order_number=order_number,
        defaults={
            "rating": rating,
            "comment": comment,
        },
    )

    if created:
        messages.success(request, "Thank you. Your verified review has been published.")
    else:
        messages.success(request, "Your review has been updated.")

    # Rare products may not belong to a HIM/HER category. Keep their
    # collection destination consistent with the product flags.
    section = getattr(product.category, "section", None) or "RARE"
    if product.is_rare or product.is_limited:
        section = "RARE"

    return redirect("section_products", section)
    
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
        # RECHECK STOCK AND PRICES, THEN CREATE ORDER
        # -----------------------------------------------
        payment_method = request.POST.get(
            "payment_method", "PREPAID"
        ).strip().upper()

        if payment_method not in ("PREPAID", "COD"):
            messages.error(request, "Please select a valid payment method.")
            return redirect("checkout")

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
                    payment_method=payment_method,
                    payment_status=(
                        "COD_PENDING" if payment_method == "COD"
                        else "PENDING"
                    ),
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

            # -------------------------------------------
            # CASH ON DELIVERY
            # -------------------------------------------
            if payment_method == "COD":
                # COD is not paid yet. Admin confirmation must recheck
                # stock before accepting/creating the shipment.
                request.session["bag"] = {}
                request.session.modified = True

                messages.success(
                    request,
                    "Your COD order has been placed. "
                    "Our team will review and confirm it shortly.",
                )

                return redirect(
                    "order_success",
                    order_number=order.order_number,
                )

            # -------------------------------------------
            # PREPAID CHECKOUT - RAZORPAY
            # -------------------------------------------
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
            logger.exception("Failed to initialize checkout")

            if order is not None:
                Order.objects.filter(
                    pk=order.pk,
                    status="PENDING",
                ).update(
                    status="CANCELLED",
                    payment_status="FAILED",
                )

            messages.error(
                request,
                "We couldn't start checkout. Please try again.",
            )
            return redirect("checkout")

        # Data consumed by the Razorpay JavaScript in checkout.html.
        # This branch is reached only for PREPAID orders.
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
            "payment_method": payment_method,
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
    Call only after verifying the Razorpay signature and confirming
    that Razorpay reports the expected payment as captured.
    """
    with transaction.atomic():
        payment = (
            Payment.objects
            .select_for_update()
            .select_related("order")
            .get(pk=payment_record.pk)
        )

        order = (
            Order.objects
            .select_for_update()
            .get(pk=payment.order_id)
        )

        # Prevent COD orders from being processed through Razorpay.
        if order.payment_method != "PREPAID":
            return False, "This order is not a prepaid order."

        # Idempotency: do not deduct stock more than once.
        if order.status == "CONFIRMED" and order.payment_status == "PAID":
            return True, "Payment already confirmed."

        order_items = list(
            OrderItem.objects
            .filter(order=order)
            .order_by("product_id")
        )

        product_ids = sorted({
            item.product_id for item in order_items
        })

        locked_products = {
            product.id: product
            for product in Product.objects
            .select_for_update()
            .filter(id__in=product_ids)
            .order_by("id")
        }

        # Check stock before deducting anything.
        insufficient = []

        for item in order_items:
            product = locked_products.get(item.product_id)

            if not product or product.stock < item.quantity:
                insufficient.append(
                    getattr(
                        product,
                        "product_name",
                        f"Product #{item.product_id}"
                    )
                )

        # Razorpay has captured the payment.
        # Record this even if inventory is insufficient.
        payment.razorpay_payment_id = razorpay_payment_id
        payment.status = "PAID"
        payment.save(update_fields=[
            "razorpay_payment_id",
            "status",
            "updated_at",
        ])

        order.payment_status = "PAID"

        if insufficient:
            order.save(update_fields=[
                "payment_status",
                "updated_at",
            ])

            return False, (
                "Payment was captured successfully, but stock is "
                "insufficient for: " + ", ".join(insufficient)
                + ". Manual fulfilment or refund is required."
            )

        # Deduct stock once, with product rows locked.
        for item in order_items:
            product = locked_products[item.product_id]
            product.stock -= item.quantity
            product.save(update_fields=["stock"])

        order.status = "CONFIRMED"

        order.save(update_fields=[
            "status",
            "payment_status",
            "updated_at",
        ])

        return True, "Payment confirmed successfully."

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

            Order.objects.filter(
                pk=payment.order_id,
                payment_status__in=["PENDING", "FAILED"],
            ).update(payment_status="PENDING")
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
    Handles Razorpay payment.captured and payment.failed events.
    Webhook secret is separate from the Razorpay API secret.
    """
    signature = request.headers.get("X-Razorpay-Signature", "")
    webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET

    if not signature or not webhook_secret:
        return HttpResponseBadRequest(
            "Missing webhook signature or secret."
        )

    try:
        client = get_razorpay_client()

        client.utility.verify_webhook_signature(
            request.body.decode("utf-8"),
            signature,
            webhook_secret,
        )

        event_data = json.loads(request.body)

    except Exception:
        logger.exception("Razorpay webhook signature verification failed")
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

    if not razorpay_order_id or not razorpay_payment_id:
        return JsonResponse({"received": True})

    try:
        payment = Payment.objects.get(
            razorpay_order_id=razorpay_order_id
        )
    except Payment.DoesNotExist:
        return JsonResponse(
            {"received": False},
            status=404,
        )

    # -----------------------------------------
    # PAYMENT FAILED
    # -----------------------------------------
    if event == "payment.failed":

        with transaction.atomic():
            payment = (
                Payment.objects
                .select_for_update()
                .get(pk=payment.pk)
            )

            order = (
                Order.objects
                .select_for_update()
                .get(pk=payment.order_id)
            )

            # Never downgrade a successfully captured payment.
            if payment.status != "PAID":
                payment.status = "FAILED"
                payment.save(update_fields=[
                    "status",
                    "updated_at",
                ])

                if order.payment_status != "PAID":
                    order.payment_status = "FAILED"
                    order.save(update_fields=[
                        "payment_status",
                        "updated_at",
                    ])

        return JsonResponse({"received": True})

    # -----------------------------------------
    # PAYMENT CAPTURED
    # -----------------------------------------

    try:
        expected_amount = int(payment.amount * 100)
        received_amount = int(entity.get("amount", -1))

    except (TypeError, ValueError):
        return HttpResponseBadRequest(
            "Invalid captured payment amount."
        )

    if (
        entity.get("status") != "captured"
        or received_amount != expected_amount
        or entity.get("currency") != payment.currency
    ):
        return HttpResponseBadRequest(
            "Captured payment details do not match."
        )

    try:
        success, message = finalize_captured_payment(
            payment,
            razorpay_payment_id,
        )

        if not success:
            # Payment may already be captured, but inventory needs
            # manual resolution or refund. Acknowledge the valid event
            # so Razorpay does not repeatedly send it.
            logger.error(
                "Razorpay captured payment needs manual resolution. "
                "Order: %s | Payment: %s | Reason: %s",
                payment.order.order_number,
                razorpay_payment_id,
                message,
            )

        return JsonResponse({
            "received": True,
            "success": success,
            "message": message,
        })

    except Exception:
        logger.exception(
            "Razorpay webhook processing failed for order %s",
            razorpay_order_id,
        )

        # Return an error so Razorpay can retry processing.
        return JsonResponse(
            {"received": False},
            status=500,
        )


def get_razorpay_client():
    key_id = settings.RAZORPAY_KEY_ID
    key_secret = settings.RAZORPAY_KEY_SECRET

    if not key_id or not key_secret:
        raise RuntimeError("Razorpay credentials are not configured.")

    return razorpay.Client(auth=(key_id, key_secret))



@csrf_exempt
@require_POST
def delivery_tracking_webhook(request):
    """
    Receive Shiprocket tracking updates.

    Configure the same token in Shiprocket's webhook settings and
    Django's SHIPROCKET_WEBHOOK_SECRET setting.
    """
    expected_token = getattr(settings, "SHIPROCKET_WEBHOOK_SECRET", "")
    received_token = request.headers.get("x-api-key", "")

    # Fail closed: never accept unsigned webhook requests.
    if not expected_token or not received_token or not hmac.compare_digest(
        str(received_token), str(expected_token)
    ):
        return JsonResponse({"received": False, "error": "Unauthorized"}, status=401)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"received": False, "error": "Invalid JSON"}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({"received": False, "error": "Invalid payload"}, status=400)

    awb = str(payload.get("awb") or payload.get("awb_code") or "").strip()
    if not awb:
        return JsonResponse({"received": False, "error": "Missing AWB"}, status=400)

    current_label = str(
        payload.get("current_status")
        or payload.get("shipment_status")
        or payload.get("status")
        or "Tracking update"
    ).strip()

    try:
        current_status_id = int(
            payload.get("shipment_status_id")
            or payload.get("current_status_id")
            or 0
        )
    except (TypeError, ValueError):
        current_status_id = 0

    scans = payload.get("scans") or []
    if not isinstance(scans, list):
        scans = []

    # Keep only JSON-serializable scan dictionaries.
    clean_scans = [scan for scan in scans if isinstance(scan, dict)]

    try:
        with transaction.atomic():
            shipment = (
                ShiprocketShipment.objects
                .select_for_update()
                .select_related("order")
                .get(awb_code=awb)
            )

            history = shipment.tracking_history or []
            if not isinstance(history, list):
                history = []

            # Add each scan only once. Shiprocket can resend the same webhook.
            known = {
                (
                    str(row.get("date", "")),
                    str(row.get("status", "")),
                    str(row.get("activity", "")),
                    str(row.get("location", "")),
                )
                for row in history if isinstance(row, dict)
            }

            for scan in clean_scans:
                key = (
                    str(scan.get("date", "")),
                    str(scan.get("status", "")),
                    str(scan.get("activity", "")),
                    str(scan.get("location", "")),
                )
                if key not in known:
                    history.append(scan)
                    known.add(key)

            shipment.courier_name = (
                payload.get("courier_name") or shipment.courier_name
            )
            shipment.current_status_label = current_label[:150]
            shipment.tracking_history = history
            shipment.estimated_delivery_date = (
                payload.get("etd") or shipment.estimated_delivery_date
            )
            # Keep response_data intact: it contains the original order/AWB
            # API response. Tracking events are stored separately above.

            # Shiprocket status IDs (shipment status codes).
            if current_status_id in (7, 10):
                shipment.status = "DELIVERED" if current_status_id == 7 else "RTO"
                if current_status_id == 7 and shipment.order.status not in ("CANCELLED",):
                    Order.objects.filter(pk=shipment.order_id).update(
                        status="DELIVERED"
                    )
            elif current_status_id in (8, 45):
                shipment.status = "CANCELLED"
            elif current_status_id in (9, 14, 40, 41, 46):
                shipment.status = "RTO"
            elif current_status_id == 17:
                shipment.status = "OUT_FOR_DELIVERY"
            elif current_status_id in (18, 38, 39, 50, 51, 54, 55, 56, 57):
                shipment.status = "IN_TRANSIT"
            elif current_status_id == 42:
                shipment.status = "PICKED_UP"
            elif current_status_id in (19, 27, 3, 4, 5):
                shipment.status = "PICKUP_PENDING"
            elif current_status_id == 6:
                shipment.status = "IN_TRANSIT"

            shipment.save(update_fields=[
                "courier_name",
                "current_status_label",
                "tracking_history",
                "estimated_delivery_date",
                "status",
                "updated_at",
            ])

            # Keep the customer-facing order status in sync for shipment
            # milestones, without ever resurrecting a cancelled order.
            if shipment.order.status != "CANCELLED":
                if shipment.status in (
                    "PICKED_UP", "IN_TRANSIT", "OUT_FOR_DELIVERY", "DELIVERED"
                ):
                    new_order_status = (
                        "DELIVERED" if shipment.status == "DELIVERED" else "SHIPPED"
                    )
                    Order.objects.filter(
                        pk=shipment.order_id
                    ).exclude(status="CANCELLED").update(status=new_order_status)

    except ShiprocketShipment.DoesNotExist:
        logger.warning("Shiprocket webhook received unknown AWB: %s", awb)
        # Acknowledge unknown AWBs so Shiprocket does not retry indefinitely.
        return JsonResponse({"received": True, "matched": False}, status=200)
    except Exception:
        logger.exception("Delivery tracking webhook processing failed for AWB %s", awb)
        return JsonResponse({"received": False}, status=500)

    return JsonResponse({"received": True, "matched": True}, status=200)


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

    shipment = getattr(order, "shipment", None)

    return render(request, "customer/order_detail.html", {
        "customer": customer,
        "order": order,
        "shipment": shipment,
        "tracking_history": (
            shipment.tracking_history
            if shipment and isinstance(shipment.tracking_history, list)
            else []
        ),
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