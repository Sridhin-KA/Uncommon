from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.customer_register, name='customer_register'),

    path('', views.customer_home, name='customer_home'),

    path(
        'collection/<str:section>/',
        views.section_products,
        name='section_products',
    ),
    path(
        "reserve-upcoming/",
        views.upcoming_reservation,
        name="upcoming_reservation",
    ),
    
path("bag/", views.bag_view, name="bag_view"),
path("bag/add/<int:product_id>/", views.add_to_bag, name="add_to_bag"),
path(
        "bag/update/<int:product_id>/",
        views.update_bag_quantity,
        name="update_bag_quantity",
    ),
    path(
        "bag/remove/<int:product_id>/",
        views.remove_from_bag,
        name="remove_from_bag",
    ),
    path("checkout/", views.checkout, name="checkout"),
path(
    "order/success/<str:order_number>/",
    views.order_success,
    name="order_success",
),
path(
    "payment/verify/",
    views.verify_razorpay_payment,
    name="verify_razorpay_payment",
),
path(
    "payment/webhook/",
    views.razorpay_webhook,
    name="razorpay_webhook",
),
path("my-orders/", views.my_orders, name="my_orders"),
path(
    "my-orders/<str:order_number>/",
    views.order_detail,
    name="order_detail",
),
path(
    "my-orders/<str:order_number>/cancel/",
    views.cancel_order,
    name="cancel_order",
),
path(
    "my-orders/<str:order_number>/cancel/",
    views.cancel_order,
    name="cancel_order",
),

path('wishlist/', views.wishlist_view, name='wishlist_view'),
path(
    'wishlist/add/<int:product_id>/',
    views.add_to_wishlist,
    name='add_to_wishlist',
),
path(
    'wishlist/remove/<int:product_id>/',
    views.remove_from_wishlist,
    name='remove_from_wishlist',
),
path(
    'wishlist/move-to-bag/<int:product_id>/',
    views.move_to_bag,
    name='move_to_bag',
),
path("profile/", views.customer_profile, name="customer_profile"),
path("profile/edit/", views.edit_customer_profile, name="edit_customer_profile"),
  path("addresses/", views.manage_address, name="manage_address"),
    path("addresses/save/", views.save_address, name="save_address"),
    path(
        "addresses/delete/<int:address_id>/",
        views.delete_address,
        name="delete_address"
    ),
]