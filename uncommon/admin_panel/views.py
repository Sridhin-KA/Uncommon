from django.shortcuts import render,redirect,get_object_or_404
from django.contrib import messages
from .models import *
from django.core.paginator import Paginator
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from customer.models import *
import json
from customer.models import *
# Create your views here.


def home(request):
    return render(request,'admin_panel/auth_page.html')



def login(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')

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
                request.session.flush()
                request.session['customer_id'] = customer.id
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

    return render(
        request,
        'admin_panel/index.html',
        {
            'admin': admin,
            'total_products': total_products,
            'total_categories': total_categories,
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
    
    if 'admin' not in request.session:
        return redirect('home')

    if request.method == 'POST':

        category_id = request.POST.get('category')
        product_name = request.POST.get('product_name', '').strip()
        description = request.POST.get('description', '').strip()
        price = request.POST.get('price', '').strip()
        stock = request.POST.get('stock', '').strip()
        image = request.FILES.get('image')

        is_rare = request.POST.get('is_rare') == 'on'
        is_limited = request.POST.get('is_limited') == 'on'

        if not category_id or not product_name:
            messages.error(
                request,
                'Category and product name are required.'
            )
            return redirect('view_products')

        if not price:
            messages.error(
                request,
                'Product price is required.'
            )
            return redirect('view_products')

        if not stock:
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

        try:
            category = Category.objects.get(
                id=category_id
            )

            price = float(price)
            stock = int(stock)

            if price < 0:
                raise ValueError

            if stock < 0:
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

        Product.objects.create(
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
            f'"{product_name}" added successfully.'
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

    order = get_object_or_404(
        Order,
        id=id
    )

    if request.method == 'POST':

        new_status = request.POST.get(
            'status',
            ''
        ).strip()

        valid_statuses = [
            'PENDING',
            'CONFIRMED',
            'SHIPPED',
            'DELIVERED',
            'CANCELLED'
        ]

        if new_status not in valid_statuses:

            messages.error(
                request,
                'Invalid order status.'
            )

            return redirect('view_orders')

        order.status = new_status

        order.save()

        messages.success(
            request,
            f'Order {order.order_number} status updated to '
            f'{order.get_status_display()}.'
        )

    return redirect('view_orders')  
def view_feedback(request):
    pass

