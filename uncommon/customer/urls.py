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
]