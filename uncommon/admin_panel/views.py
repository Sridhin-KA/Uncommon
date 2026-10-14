from django.shortcuts import render,redirect,get_object_or_404
from django.contrib import messages
from .models import *
from django.core.paginator import Paginator
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from customer.models import *
import json
from customer.models import *
from django.core.mail import send_mail
from django.conf import settings
from decimal import Decimal, InvalidOperation
# Create your views here.


def home(request):
    return render(request,'admin_panel/auth_page.html')





def login(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')

        # Save guest bag and intended destination before login
        guest_bag = request.session.get('bag', {})
        next_page = request.session.get(
            'next_after_login',
            'customer_home'
        )

        # 1. Check Admin
        try:
            admin = Admin.objects.get(email=email)

            if admin.password == password:
                request.session.flush()
                request.session['admin'] = admin.id

                return redirect('admin_index')

        except Admin.DoesNotExist:
            pass

        # 2. Check Customer
        try:
            customer = Customer.objects.get(email=email)

            if customer.password == password:
                # Clear old session data
                request.session.flush()

                # Restore customer session
                request.session['customer_id'] = customer.id
                request.session['bag'] = guest_bag

                # Redirect to the intended page
                if next_page == 'checkout':
                    return redirect('checkout')

                return redirect('customer_home')

        except Customer.DoesNotExist:
            pass

        # 3. Invalid credentials
        return render(
            request,
            'admin_panel/auth_page.html',
            {'error': 'Invalid email or password'}
        )

    return render(request, 'admin_panel/auth_page.html')

def admin_index(request):
    
    if 'admin' not in request.session:
        return redirect('home')

    admin = Admin.objects.get(
        id=request.session['admin']
    )

    total_products = Product.objects.count()
    total_categories = Category.objects.count()
    total_customers = Customer.objects.count()
    total_orders = Order.objects.count()

    return render(
        request,
        'admin_panel/index.html',
        {
            'admin': admin,
            'total_products': total_products,
            'total_categories': total_categories,
            'total_customers': total_customers,
            'total_orders': total_orders,
        }
    )


def admin_logout(request):
    if 'admin' in request.session:
        del request.session['admin']
    elif 'customer_id' in request.session:
        del request.session['customer_id']
    return render(request, 'admin_panel/auth_page.html')

# =========================
# CATEGORY MANAGEMENT
# =========================

def view_categories(request):

    if 'admin' not in request.session:
        return redirect('home')

    admin = get_object_or_404(
        Admin,
        id=request.session['admin']
    )

    categories = Category.objects.all().order_by('-id')

    # Search
    search = request.GET.get('search', '').strip()

    if search:
        categories = categories.filter(
            category_name__icontains=search
        )


    # Section filter
    section = request.GET.get('section', '').strip()

    if section in ['HIM', 'HER', 'RARE']:
        categories = categories.filter(
            section=section
        )


    # Pagination
    

    paginator = Paginator(categories, 10)

    page_number = request.GET.get('page')

    page_obj = paginator.get_page(page_number)


    return render(
        request,
        'admin_panel/categories.html',
        {
            'admin': admin,
            'page_obj': page_obj,
            'search': search,
            'section': section,
        }
    )


# =========================
# ADD CATEGORY
# =========================

def add_category(request):

    if 'admin' not in request.session:
        return redirect('home')

    if request.method == 'POST':

        section = request.POST.get('section')
        category_name = request.POST.get('category_name')
        description = request.POST.get('description')

        if not section or not category_name:

            messages.error(
                request,
                'Section and category name are required.'
            )

            return redirect('view_categories')


        Category.objects.create(
            section=section,
            category_name=category_name,
            description=description
        )

        messages.success(
            request,
            f'"{category_name}" category added successfully.'
        )

    return redirect('view_categories')


# =========================
# EDIT CATEGORY
# =========================

def edit_category(request, id):

    if 'admin' not in request.session:
        return redirect('home')

    category = get_object_or_404(
        Category,
        id=id
    )

    if request.method == 'POST':

        section = request.POST.get('section')
        category_name = request.POST.get('category_name')
        description = request.POST.get('description')

        if not section or not category_name:

            messages.error(
                request,
                'Section and category name are required.'
            )

            return redirect('view_categories')


        category.section = section
        category.category_name = category_name
        category.description = description

        category.save()

        messages.success(
            request,
            f'"{category_name}" category updated successfully.'
        )

    return redirect('view_categories')


# =========================
# DELETE CATEGORY
# =========================

def delete_category(request, id):
    
    if 'admin' not in request.session:
        return redirect('home')

    category = get_object_or_404(
        Category,
        id=id
    )

    if request.method == 'POST':

        category_name = category.category_name

        try:

            category.delete()

            messages.success(
                request,
                f'"{category_name}" deleted successfully.'
            )

        except ProtectedError:

            messages.error(
                request,
                f'Cannot delete "{category_name}" because products are using this category.'
            )

    return redirect('view_categories')

def view_products(request):
    if 'admin' not in request.session:
        return redirect('home')

    admin = get_object_or_404(
        Admin,
        id=request.session['admin']
    )

    categories = Category.objects.all().order_by(
        'section',
        'category_name'
    )

    products = Product.objects.select_related(
        'category'
    ).all().order_by('-id')

    search = request.GET.get('search', '').strip()

    if search:
        products = products.filter(
            Q(product_name__icontains=search) |
            Q(description__icontains=search)
        )

    section = request.GET.get('section', '').strip()

    if section in ['HIM', 'HER', 'RARE']:
        products = products.filter(
            category__section=section
        )

    category_id = request.GET.get(
        'category',
        ''
    ).strip()

    if category_id:
        products = products.filter(
            category_id=category_id
        )

    low_stock_count = Product.objects.filter(
        stock__gt=0,
        stock__lte=5
    ).count()

    out_of_stock_count = Product.objects.filter(
        stock=0
    ).count()

    # PAGINATION
    paginator = Paginator(
        products,
        5
    )

    page_number = request.GET.get(
        'page'
    )

    page_obj = paginator.get_page(
        page_number
    )


    return render(
        request,
        'admin_panel/products.html',
        {
            'admin': admin,
            'page_obj': page_obj,
            'categories': categories,
            'search': search,
            'section': section,
            'category_id': category_id,
            'low_stock_count': low_stock_count,
            'out_of_stock_count': out_of_stock_count,
        }
    )
    

def add_product(request):

    # Admin authentication
    if 'admin' not in request.session:
        return redirect('home')

    # Get submitted values
    category_id = request.POST.get('category', '').strip()
    product_name = request.POST.get('product_name', '').strip()
    description = request.POST.get('description', '').strip()
    price_input = request.POST.get('price', '').strip()
    stock_input = request.POST.get('stock', '').strip()
    image = request.FILES.get('image')

    is_rare = request.POST.get('is_rare') == 'on'
    is_limited = request.POST.get('is_limited') == 'on'

    # Validate required fields
    if not category_id or not product_name:
        messages.error(
            request,
            'Category and product name are required.'
        )
        return redirect('view_products')

    if len(product_name) > 255:
        messages.error(
            request,
            'Product name is too long.'
        )
        return redirect('view_products')

    if not price_input:
        messages.error(
            request,
            'Product price is required.'
        )
        return redirect('view_products')

    if not stock_input:
        messages.error(
            request,
            'Product stock is required.'
        )
        return redirect('view_products')

    if not image:
        messages.error(
            request,
            'Product image is required.'
        )
        return redirect('view_products')

    # Validate category, price and stock
    try:
        category = Category.objects.get(id=category_id)

        price = Decimal(price_input)
        stock = int(stock_input)

        if not price.is_finite() or price < 0:
            raise ValueError

        if stock < 0:
            raise ValueError

    except Category.DoesNotExist:
        messages.error(
            request,
            'Selected category does not exist.'
        )
        return redirect('view_products')

    except (InvalidOperation, ValueError, TypeError):
        messages.error(
            request,
            'Please enter valid price and stock values.'
        )
        return redirect('view_products')

    # Create the product
    product = Product.objects.create(
        category=category,
        product_name=product_name,
        description=description,
        price=price,
        stock=stock,
        image=image,
        is_rare=is_rare,
        is_limited=is_limited,
    )

    messages.success(
        request,
        f'"{product.product_name}" added successfully.'
    )

    # Send availability notifications only when stock is available
    if product.stock <= 0:
        messages.info(
            request,
            'The product has no stock yet, so subscriber emails were not sent.'
        )
        return redirect('view_products')

    # Build the list of matching subscriber interests
    matching_interests = [
        'New product launch',
        'Any upcoming release',
    ]

    if product.is_rare:
        matching_interests.append(
            'The Hundred — next rare release'
        )

    if product.is_limited:
        matching_interests.append(
            'Limited-edition product'
        )

    # Get matching subscribers
    subscribers = UpcomingReservation.objects.filter(
        interest__in=matching_interests
    ).order_by('id')

    # Notify each email address only once for this product creation
    subscriber_emails = (
        subscribers
        .values_list('email', flat=True)
        .distinct()
    )

    email_sent = 0
    email_failed = 0

    subject = (
        f'INSOLO UNCOMMON | New Release: {product.product_name}'
    )

    for email in subscriber_emails:

        # Find a subscriber record for the greeting
        subscriber = subscribers.filter(
            email=email
        ).first()

        customer_name = subscriber.name if subscriber else 'Customer'

        body = f"""
Hello {customer_name},

Good news! A new product matching your interests is now available.

Product: {product.product_name}
Price: ₹{product.price}

Your interest: {subscriber.interest if subscriber else 'Upcoming release'}

Visit INSOLO UNCOMMON to explore our latest collection.

Thank you for your interest.

INSOLO UNCOMMON — The House
        """.strip()

        try:
            send_mail(
                subject=subject,
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )

            email_sent += 1

        except Exception:
            email_failed += 1

    # Report notification results to the admin
    if email_sent:
        messages.success(
            request,
            f'Availability notification sent to {email_sent} subscriber(s).'
        )

    if email_failed:
        messages.warning(
            request,
            f'{email_failed} notification email(s) could not be sent.'
        )

    if email_sent == 0 and email_failed == 0:
        messages.info(
            request,
            'No subscribers matched this product.'
        )

    return redirect('view_products')


def edit_product(request, id):
    
    if 'admin' not in request.session:
        return redirect('home')

    product = get_object_or_404(
        Product,
        id=id
    )

    if request.method == 'POST':

        category_id = request.POST.get('category')
        product_name = request.POST.get(
            'product_name',
            ''
        ).strip()

        description = request.POST.get(
            'description',
            ''
        ).strip()

        price = request.POST.get(
            'price',
            ''
        ).strip()

        stock = request.POST.get(
            'stock',
            ''
        ).strip()

        image = request.FILES.get('image')

        is_rare = request.POST.get(
            'is_rare'
        ) == 'on'

        is_limited = request.POST.get(
            'is_limited'
        ) == 'on'

        if not category_id or not product_name:
            messages.error(
                request,
                'Category and product name are required.'
            )
            return redirect('view_products')

        try:

            category = Category.objects.get(
                id=category_id
            )

            price = float(price)
            stock = int(stock)

            if price < 0 or stock < 0:
                raise ValueError

        except Category.DoesNotExist:

            messages.error(
                request,
                'Selected category does not exist.'
            )

            return redirect('view_products')

        except ValueError:

            messages.error(
                request,
                'Please enter valid price and stock values.'
            )

            return redirect('view_products')

        product.category = category
        product.product_name = product_name
        product.description = description
        product.price = price
        product.stock = stock
        product.is_rare = is_rare
        product.is_limited = is_limited

        # Only replace image if a new image was uploaded
        if image:
            product.image = image

        product.save()

        messages.success(
            request,
            f'"{product_name}" updated successfully.'
        )

    return redirect('view_products')


def delete_product(request, id):
    
    if 'admin' not in request.session:
        return redirect('home')

    product = get_object_or_404(
        Product,
        id=id
    )

    if request.method == 'POST':

        product_name = product.product_name

        product.delete()

        messages.success(
            request,
            f'"{product_name}" deleted successfully.'
        )

    return redirect('view_products')


def view_customers(request):
    
    if 'admin' not in request.session:
        return redirect('home')

    admin = get_object_or_404(
        Admin,
        id=request.session['admin']
    )

    customers = Customer.objects.all().order_by('-id')

    # Search
    search = request.GET.get('search', '').strip()

    if search:
        customers = customers.filter(
            Q(name__icontains=search) |
            Q(email__icontains=search) |
            Q(username__icontains=search) |
            Q(phone__icontains=search)
        )

    # Total customers
    total_customers = Customer.objects.count()

    # Pagination
    paginator = Paginator(customers, 10)

    page_obj = paginator.get_page(
        request.GET.get('page')
    )

    return render(
        request,
        'admin_panel/customers.html',
        {
            'admin': admin,
            'page_obj': page_obj,
            'search': search,
            'total_customers': total_customers,
        }
    )


def edit_customer(request, id):

    if 'admin' not in request.session:
        return redirect('home')

    customer = get_object_or_404(
        Customer,
        id=id
    )

    if request.method == 'POST':

        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        username = request.POST.get('username', '').strip()

        if not name or not email or not username:
            messages.error(
                request,
                'Name, email and username are required.'
            )
            return redirect('view_customers')

        # Check duplicate email
        if Customer.objects.filter(
            email=email
        ).exclude(id=id).exists():

            messages.error(
                request,
                'This email is already registered.'
            )
            return redirect('view_customers')

        # Check duplicate username
        if Customer.objects.filter(
            username=username
        ).exclude(id=id).exists():

            messages.error(
                request,
                'This username is already taken.'
            )
            return redirect('view_customers')

        customer.name = name
        customer.email = email
        customer.phone = phone
        customer.username = username

        customer.save()

        messages.success(
            request,
            f'"{customer.name}" updated successfully.'
        )

    return redirect('view_customers')


def delete_customer(request, id):

    if 'admin' not in request.session:
        return redirect('home')

    customer = get_object_or_404(
        Customer,
        id=id
    )

    if request.method == 'POST':

        customer_name = customer.name

        customer.delete()

        messages.success(
            request,
            f'"{customer_name}" deleted successfully.'
        )

    return redirect('view_customers')




def view_orders(request):
    
    if 'admin' not in request.session:
        return redirect('home')

    admin = get_object_or_404(
        Admin,
        id=request.session['admin']
    )

    orders = Order.objects.select_related(
        'customer'
    ).prefetch_related(
        'items__product'
    ).all().order_by('-created_at')

    # ==============================
    # SEARCH
    # ==============================

    search = request.GET.get('search', '').strip()

    if search:

        orders = orders.filter(
            Q(order_number__icontains=search) |
            Q(customer__name__icontains=search) |
            Q(customer__email__icontains=search)
        )

    # ==============================
    # STATUS FILTER
    # ==============================

    status = request.GET.get('status', '').strip()

    valid_statuses = [
        'PENDING',
        'CONFIRMED',
        'SHIPPED',
        'DELIVERED',
        'CANCELLED'
    ]

    if status in valid_statuses:

        orders = orders.filter(
            status=status
        )

    # ==============================
    # STATISTICS
    # ==============================

    total_orders = Order.objects.count()

    pending_orders = Order.objects.filter(
        status='PENDING'
    ).count()

    confirmed_orders = Order.objects.filter(
        status='CONFIRMED'
    ).count()

    shipped_orders = Order.objects.filter(
        status='SHIPPED'
    ).count()

    delivered_orders = Order.objects.filter(
        status='DELIVERED'
    ).count()

    cancelled_orders = Order.objects.filter(
        status='CANCELLED'
    ).count()

    # ==============================
    # PAGINATION
    # ==============================

    paginator = Paginator(
        orders,
        10
    )

    page_obj = paginator.get_page(
        request.GET.get('page')
    )

    # ==============================
    # ORDER ITEMS DATA
    # ==============================

    order_items_data = {}

    for order in page_obj:

        items = []

        for item in order.items.all():

            items.append({
                'product': item.product.product_name,
                'quantity': item.quantity,
                'price': float(item.price),
                'total': float(
                    item.price * item.quantity
                )
            })

        order_items_data[str(order.id)] = items

    return render(
        request,
        'admin_panel/orders.html',
        {
            'admin': admin,

            'page_obj': page_obj,

            'search': search,
            'status': status,

            'total_orders': total_orders,
            'pending_orders': pending_orders,
            'confirmed_orders': confirmed_orders,
            'shipped_orders': shipped_orders,
            'delivered_orders': delivered_orders,
            'cancelled_orders': cancelled_orders,

            'order_items_json': json.dumps(
                order_items_data
            ),
        }
    )
    
def update_order_status(request, id):
    
    if 'admin' not in request.session:
        return redirect('home')

    order = get_object_or_404(Order, id=id)

    if request.method == 'POST':

        new_status = request.POST.get('status', '').strip()

        valid_statuses = [
            'PENDING',
            'CONFIRMED',
            'SHIPPED',
            'DELIVERED',
            'CANCELLED'
        ]

        if new_status not in valid_statuses:
            messages.error(request, 'Invalid order status.')
            return redirect('view_orders')

        old_status = order.status

        # Update only if the status has actually changed.
        if new_status == old_status:
            messages.info(
                request,
                'The order already has this status.'
            )
            return redirect('view_orders')

        order.status = new_status
        order.save(update_fields=['status', 'updated_at'])

        # Get the customer's email address.
        customer_email = order.customer.email

        if customer_email:
            status_messages = {
                'PENDING': (
                    'Your order is pending.',
                    'We have received your order and it is awaiting confirmation.'
                ),
                'CONFIRMED': (
                    'Your order has been confirmed!',
                    'Great news! Your order has been confirmed and is being prepared.'
                ),
                'SHIPPED': (
                    'Your order has been shipped!',
                    'Your order is on its way. We will keep you updated.'
                ),
                'DELIVERED': (
                    'Your order has been delivered!',
                    'Your order has been marked as delivered. We hope you love your purchase!'
                ),
                'CANCELLED': (
                    'Your order has been cancelled.',
                    'Your order has been cancelled. Please contact us if you need assistance.'
                ),
            }

            subject_text, message_text = status_messages[new_status]

            subject = f'UNCOMMON | {subject_text}'

            email_body = f"""
Hello {getattr(order.customer, 'name', '') or 'Customer'},

{message_text}

Order Number: {order.order_number}
Order Total: ₹{order.total_amount}
Current Status: {order.get_status_display()}

Thank you for choosing UNCOMMON.

Regards,
 UNCOMMON Team
            """.strip()

            try:
                send_mail(
                    subject=subject,
                    message=email_body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[customer_email],
                    fail_silently=False,
                )

                messages.success(
                    request,
                    f'Order status updated and email sent to {customer_email}.'
                )

            except Exception:
                # The status is already saved even if email delivery fails.
                messages.warning(
                    request,
                    'Order status updated, but the email could not be sent.'
                )

        else:
            messages.warning(
                request,
                'Order status updated, but the customer has no email address.'
            )

        return redirect('view_orders')

    return redirect('view_orders')

def view_feedback(request):
    pass



from django.conf import settings
from django.http import JsonResponse
from django.core.mail import send_mail

def test_email(request):
    if 'admin' not in request.session:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    try:
        sent = send_mail(
            subject="Render Email Test",
            message="Testing email from Django on Render.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.EMAIL_HOST_USER],
            fail_silently=False,
        )

        return JsonResponse({"sent": sent})

    except Exception as e:
        import logging
        logging.exception("Email test failed")
        return JsonResponse({
            "error": type(e).__name__,
            "message": str(e),
        }, status=500)