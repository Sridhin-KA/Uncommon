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
from django.http import JsonResponse
import uuid

from django.db import transaction
from django.db.models import F


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

    if section not in ['HIM', 'HER', 'RARE']:
        from django.http import Http404
        raise Http404('Section not found')

    products = Product.objects.select_related(
        'category'
    ).filter(stock__gt=0)

    if section == 'RARE':
        products = products.filter(
            Q(is_rare=True) | Q(is_limited=True)
        )
        title = 'The Hundred'
        subtitle = 'Rare objects. Limited numbers. Never ordinary.'
    else:
        products = products.filter(
            category__section=section
        )
        title = 'Him' if section == 'HIM' else 'Insolo — Her'
        subtitle = (
            'Objects selected for him.'
            if section == 'HIM'
            else 'A different kind of uncommon.'
        )

    search = request.GET.get('search', '').strip()

    if search:
        products = products.filter(
            Q(product_name__icontains=search) |
            Q(description__icontains=search) |
            Q(category__category_name__icontains=search)
        )

    products = products.order_by('-created_at')

    return render(request, 'customer/section_products.html', {
        'section': section,
        'title': title,
        'subtitle': subtitle,
        'products': products,
        'search': search,
    })
    customer_id = request.session.get('customer_id')

    if not customer_id:
        return render(
            request,
            'customer/home.html',
            {'customer': None}
        )

    customer = Customer.objects.get(id=customer_id)

    return render(
        request,
        'customer/home.html',
        {'customer': customer}
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



def checkout(request):
    customer = get_logged_in_customer(request)

    if not customer:
        # Remember where the guest wants to go after login
        request.session["next_after_login"] = "checkout"
        request.session.modified = True

        messages.info(request, "Please log in before checkout.")
        return redirect("login")

    bag = request.session.get("bag", {})

    if not bag:
        messages.info(request, "Your bag is empty.")
        return redirect("bag_view")

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
                f"Only {product.stock} of {product.product_name} are available."
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
        messages.error(request, "Your bag contains no available products.")
        return redirect("bag_view")

    if request.method == "POST":
        shipping_address = request.POST.get("shipping_address", "").strip()

        if not shipping_address:
            messages.error(request, "Please enter your shipping address.")
            return render(request, "customer/checkout.html", {
                "customer": customer,
                "items": items,
                "total": total,
            })

        if len(shipping_address) > 2000:
            messages.error(request, "Please shorten your shipping address.")
            return render(request, "customer/checkout.html", {
                "customer": customer,
                "items": items,
                "total": total,
            })

        with transaction.atomic():
            order_items_to_create = []

            # Lock and re-check each product to avoid overselling.
            product_ids = sorted(
                int(item["product"].id) for item in items
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
                product_id = item["product"].id
                product = locked_products.get(product_id)
                quantity = item["quantity"]

                if not product or product.stock < quantity:
                    messages.error(
                        request,
                        f"Insufficient stock for {item['product'].product_name}. "
                        "Please review your bag."
                    )
                    return redirect("bag_view")

                verified_items.append((product, quantity))
                verified_total += product.price * quantity

            order = Order.objects.create(
                customer=customer,
                order_number=f"INS-{uuid.uuid4().hex[:12].upper()}",
                total_amount=verified_total,
                shipping_address=shipping_address,
                status="PENDING",
            )

            for product, quantity in verified_items:
                order_items_to_create.append(
                    OrderItem(
                        order=order,
                        product=product,
                        quantity=quantity,
                        price=product.price,
                    )
                )

                Product.objects.filter(pk=product.pk).update(
                    stock=F("stock") - quantity
                )

            OrderItem.objects.bulk_create(order_items_to_create)

        request.session["bag"] = {}
        request.session.modified = True

        return redirect("order_success", order_number=order.order_number)

    return render(request, "customer/checkout.html", {
        "customer": customer,
        "items": items,
        "total": total,
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

    return render(request, "customer/profile.html", {
        "customer": customer,
        "orders": orders,
        "total_orders": orders.count(),
        "delivered_orders": orders.filter(status="DELIVERED").count(),
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