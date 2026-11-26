from django.db import models
from django.db import models
from django.core.validators import RegexValidator

# Create your models here.

class Customer(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20)
    username = models.CharField(max_length=100, unique=True)
    password = models.CharField(max_length=255)

    def __str__(self):
        return self.name
    


class CustomerAddress(models.Model):
    customer = models.ForeignKey(
        "Customer",
        on_delete=models.CASCADE,
        related_name="saved_addresses"
    )

    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15)

    address_line = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)

    pincode = models.CharField(
        max_length=6,
        validators=[
            RegexValidator(
                regex=r"^[0-9]{6}$",
                message="Enter a valid 6-digit Indian PIN code."
            )
        ]
    )

    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.city}"

class Order(models.Model):

    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("CONFIRMED", "Confirmed"),
        ("SHIPPED", "Shipped"),
        ("DELIVERED", "Delivered"),
        ("CANCELLED", "Cancelled"),
    ]

    PAYMENT_METHOD_CHOICES = [
        ("PREPAID", "Prepaid"),
        ("COD", "Cash on Delivery"),
    ]

    PAYMENT_STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("PAID", "Paid"),
        ("COD_PENDING", "COD Pending"),
        ("FAILED", "Failed"),
    ]

    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="orders",
    )

    order_number = models.CharField(max_length=30, unique=True)

    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default="PREPAID",
    )

    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default="PENDING",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="PENDING",
    )

    shipping_address = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.order_number


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
    )

    product = models.ForeignKey(
        'admin_panel.Product',
        on_delete=models.PROTECT,
    )

    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.order.order_number} - {self.product.product_name}"

class ShiprocketShipment(models.Model):
    
    STATUS_CHOICES = [
        ("NOT_CREATED", "Not Created"),
        ("CREATED", "Created"),
        ("PICKUP_PENDING", "Pickup Pending"),
        ("PICKED_UP", "Picked Up"),
        ("IN_TRANSIT", "In Transit"),
        ("OUT_FOR_DELIVERY", "Out for Delivery"),
        ("DELIVERED", "Delivered"),
        ("CANCELLED", "Cancelled"),
        ("RTO", "Return to Origin"),
        ("FAILED", "Failed"),
    ]

    order = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        related_name="shipment"
    )

    shiprocket_order_id = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    shipment_id = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    awb_code = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    courier_name = models.CharField(
        max_length=150,
        blank=True,
        null=True
    )

    tracking_url = models.URLField(
        max_length=500,
        blank=True,
        null=True
    )

    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default="NOT_CREATED"
    )

    request_data = models.JSONField(
        blank=True,
        null=True
    )

    response_data = models.JSONField(
        blank=True,
        null=True
    )

    error_message = models.TextField(
        blank=True,
        null=True
    )

    # Latest courier label and event history received from Shiprocket.
    current_status_label = models.CharField(max_length=150, blank=True)
    estimated_delivery_date = models.CharField(max_length=100, blank=True)
    tracking_history = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Shipment - {self.order.order_number}"

class Payment(models.Model):
    STATUS_CHOICES = [
        ("CREATED", "Created"),
        ("PENDING", "Pending"),
        ("PAID", "Paid"),
        ("FAILED", "Failed"),
    ]

    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    razorpay_order_id = models.CharField(
        max_length=100,
        unique=True,
    )
    razorpay_payment_id = models.CharField(
        max_length=100,
        unique=True,
        null=True,
        blank=True,
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="INR")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="CREATED",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    REFUND_STATUS_CHOICES = [
    ("NONE", "No refund"),
    ("PENDING", "Refund pending"),
    ("PROCESSED", "Refund processed"),
    ("FAILED", "Refund failed"),
    ]

    refund_status = models.CharField(
        max_length=20,
        choices=REFUND_STATUS_CHOICES,
        default="NONE",
    )
    razorpay_refund_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )
    def __str__(self):
        return f"{self.order.order_number} - {self.status}"
        
class UpcomingReservation(models.Model):
    name = models.CharField(max_length=120)
    email = models.EmailField()
    interest = models.CharField(max_length=150)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} — {self.interest}"

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Upcoming Reservation"
        verbose_name_plural = "Upcoming Reservations"
        
class TaxInvoice(models.Model):
    order = models.OneToOneField(
        "Order",
        on_delete=models.PROTECT,
        related_name="tax_invoice"
    )
    invoice_number = models.CharField(max_length=40, unique=True)
    pdf = models.FileField(upload_to="invoices/%Y/%m/", blank=True)
    email_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.invoice_number