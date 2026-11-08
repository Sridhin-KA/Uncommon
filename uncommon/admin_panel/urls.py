from django.urls import path

from admin_panel import views

urlpatterns = [
    # ---- Auth ---------------------------------------------------------------
    path("first", views.home, name="home"),
    path("login", views.login, name="login"),
    path("logout/", views.admin_logout, name="admin_logout"),
    path("verify-finance-access/", views.verify_finance_password, name="verify_finance_password"),

    # ---- Dashboard ----------------------------------------------------------
    path("index/", views.admin_index, name="admin_index"),

    # ---- Financial and tax reports -------------------------------------------
    path("api/admin/finance/weekly/", views.admin_finance_weekly, name="admin_finance_weekly"),
    path("api/admin/finance/gst/", views.admin_tax_gst, name="admin_tax_gst"),
    path("finance/gst/<str:table>.csv", views.admin_tax_csv, name="admin_tax_csv"),
    path("finance/ledger/<str:fy>.csv", views.admin_ledger_csv, name="admin_ledger_csv"),

    # ---- Customers ----------------------------------------------------------
    path("customers/", views.view_customers, name="view_customers"),
    path("customers/edit/<int:id>/", views.edit_customer, name="edit_customer"),
    path("customers/delete/<int:id>/", views.delete_customer, name="delete_customer"),

    # ---- Products -----------------------------------------------------------
    path("products/", views.view_products, name="view_products"),
    path("products/add/", views.add_product, name="add_product"),
    path("products/edit/<int:id>/", views.edit_product, name="edit_product"),
    path("products/delete/<int:id>/", views.delete_product, name="delete_product"),

    # ---- Categories ---------------------------------------------------------
    path("categories/", views.view_categories, name="view_categories"),
    path("categories/add/", views.add_category, name="add_category"),
    path("categories/edit/<int:id>/", views.edit_category, name="edit_category"),
    path("categories/delete/<int:id>/", views.delete_category, name="delete_category"),

    # ---- Orders -------------------------------------------------------------
    path("orders/", views.view_orders, name="view_orders"),
    path("orders/status/<int:id>/", views.update_order_status, name="update_order_status"),

    # ---- Feedback -----------------------------------------------------------
    path("view_feedback", views.admin_feedback, name="admin_feedback"),
    path(
        "feedback/add/<str:order_number>/<int:product_id>/",
        views.add_feedback,
        name="add_feedback",
    ),
    path("feedback/delete/<int:feedback_id>/", views.delete_feedback, name="delete_feedback"),

    # ---- Purchasing ---------------------------------------------------------
    path("purchases/", views.purchases, name="purchases"),
    path("purchases/create/", views.create_purchase_order, name="create_purchase_order"),
    path(
        "purchases/<int:po_id>/update-status/",
        views.update_purchase_status,
        name="update_purchase_status",
    ),

    # Suppliers
    path("purchases/suppliers/create/", views.supplier_create, name="supplier_create"),
    path(
        "purchases/suppliers/<int:supplier_id>/update/",
        views.supplier_update,
        name="supplier_update",
    ),
    path(
        "purchases/suppliers/<int:supplier_id>/toggle/",
        views.supplier_toggle,
        name="supplier_toggle",
    ),

    # Purchase orders (full form), goods receipts, bills, payments
    path("purchases/orders/create/", views.purchase_order_create, name="purchase_order_create"),
    path(
        "purchases/orders/<int:po_id>/status/",
        views.purchase_order_status_update,
        name="purchase_order_status_update",
    ),
    path("purchases/receipts/create/", views.goods_receipt_create, name="goods_receipt_create"),
    path("purchases/bills/create/", views.vendor_bill_create, name="vendor_bill_create"),
    path("purchases/payments/create/", views.vendor_payment_create, name="vendor_payment_create"),

    # ---- Utilities ----------------------------------------------------------
    path("uncommen/", views.admin_login, name="admin_login"),
    path("test-email/", views.test_email, name="test_email"),
]