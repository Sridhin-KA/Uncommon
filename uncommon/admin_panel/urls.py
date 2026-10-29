from django.contrib import admin
from django.urls import path,include
from admin_panel.views import *

urlpatterns = [
    path('first',home,name='home'),
    path('login',login,name='login'),
    path('logout/', admin_logout, name='admin_logout'),
    path('index/', admin_index, name='admin_index'),
     path(
        "api/admin/finance/weekly/",
        admin_finance_weekly,
        name="admin_finance_weekly",
    ),
    path('customers/', view_customers, name='view_customers'),
path('customers/edit/<int:id>/', edit_customer, name='edit_customer'),
path('customers/delete/<int:id>/', delete_customer, name='delete_customer'),
   path(
    'products/',
   view_products,
    name='view_products'
),

path(
    'products/add/',
   add_product,
    name='add_product'
),

path(
    'products/edit/<int:id>/',
    edit_product,
    name='edit_product'
),

path(
    'products/delete/<int:id>/',
    delete_product,
    name='delete_product'
),
    path('categories/', view_categories, name='view_categories'),
    path('categories/add/', add_category, name='add_category'),
    path('categories/edit/<int:id>/', edit_category, name='edit_category'),
    path( 'categories/delete/<int:id>/', delete_category, name='delete_category'),
   path('orders/', view_orders, name='view_orders'),

path(
    'orders/status/<int:id>/',
    update_order_status,
    name='update_order_status'
),
   path(
    'feedback/add/<str:order_number>/<int:product_id>/',
    add_feedback,
    name='add_feedback'
),
   
path(
    'feedback/delete/<int:feedback_id>/',
    delete_feedback,
    name='delete_feedback'
),
    path('test-email/', test_email, name='test_email'),
    path(
    "purchases/create/",
   create_purchase_order,
    name="create_purchase_order",
),
    path('view_feedback',view_feedback,name='view_feedback')
]
