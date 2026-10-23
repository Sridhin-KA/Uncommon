from django.db import models

# Create your models here.


class Admin(models.Model):
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=255)

    def __str__(self):
        return self.email


class Category(models.Model):

    SECTION_CHOICES = [
        ('HIM', 'Him'),
        ('HER', 'Her'),
        ('RARE', 'Rare'),
    ]

    section = models.CharField(
        max_length=10,
        choices=SECTION_CHOICES
    )

    category_name = models.CharField(
        max_length=100
    )

    description = models.TextField(
        blank=True
    )

    def __str__(self):
        return f"{self.section} - {self.category_name}"
    
    
class Product(models.Model):
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='products'
    )

    product_name = models.CharField(max_length=150)

    description = models.TextField(blank=True)

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    stock = models.PositiveIntegerField(default=0)

    image = models.ImageField(
        upload_to='products/',
        blank=True,
        null=True
    )

    is_rare = models.BooleanField(default=False)

    is_limited = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.product_name
    
    

class Wishlist(models.Model):
    customer = models.ForeignKey(
        'customer.Customer',
        on_delete=models.CASCADE,
        related_name='wishlist_items'
    )

    product = models.ForeignKey(
        'admin_panel.Product',
        on_delete=models.CASCADE,
        related_name='wishlisted_by'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['customer', 'product'],
                name='unique_customer_wishlist_product'
            )
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.customer} - {self.product.product_name}"
    
    
    
class Feedback(models.Model):
    customer = models.ForeignKey(
        'customer.Customer',
        on_delete=models.CASCADE,
        related_name='feedbacks'
    )

    product = models.ForeignKey(
        'admin_panel.Product',
        on_delete=models.CASCADE,
        related_name='feedbacks'
    )

    # References the order number for which the product was delivered.
    order_number = models.CharField(max_length=50)

    rating = models.PositiveSmallIntegerField()

    comment = models.TextField(max_length=1000)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['customer', 'product', 'order_number'],
                name='unique_customer_product_order_feedback'
            ),
            models.CheckConstraint(
                condition=models.Q(rating__gte=1, rating__lte=5),
                name='feedback_rating_between_1_and_5'
            ),
        ]

    def __str__(self):
        return f'{self.customer} - {self.product} ({self.rating}/5)'
    
    
# models.py
# Add these models alongside your existing Product model.

from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone


ZERO = Decimal("0.00")


class Supplier(models.Model):
    """Supplier / vendor master."""

    supplier_code = models.CharField(max_length=30, unique=True)
    company_name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    alternate_phone = models.CharField(max_length=20, blank=True)
    website = models.URLField(blank=True)

    gstin = models.CharField(max_length=15, blank=True, db_index=True)
    pan_number = models.CharField(max_length=10, blank=True)
    tax_registration_type = models.CharField(
        max_length=30,
        choices=[
            ("registered", "Regular Registered"),
            ("composition", "Composition"),
            ("unregistered", "Unregistered"),
            ("overseas", "Overseas"),
        ],
        default="registered",
    )

    billing_address = models.TextField(blank=True)
    billing_city = models.CharField(max_length=100, blank=True)
    billing_state = models.CharField(max_length=100, blank=True)
    billing_state_code = models.CharField(max_length=2, blank=True)
    billing_postal_code = models.CharField(max_length=10, blank=True)
    billing_country = models.CharField(max_length=100, default="India")

    shipping_address = models.TextField(blank=True)
    shipping_city = models.CharField(max_length=100, blank=True)
    shipping_state = models.CharField(max_length=100, blank=True)
    shipping_postal_code = models.CharField(max_length=10, blank=True)
    shipping_country = models.CharField(max_length=100, default="India")

    payment_terms_days = models.PositiveIntegerField(default=30)
    credit_limit = models.DecimalField(
        max_digits=14, decimal_places=2, default=ZERO
    )
    opening_balance = models.DecimalField(
        max_digits=14, decimal_places=2, default=ZERO
    )

    bank_name = models.CharField(max_length=150, blank=True)
    bank_account_name = models.CharField(max_length=150, blank=True)
    bank_account_number = models.CharField(max_length=50, blank=True)
    bank_ifsc = models.CharField(max_length=11, blank=True)
    bank_branch = models.CharField(max_length=150, blank=True)

    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["company_name"]

    def __str__(self):
        return f"{self.supplier_code} - {self.company_name}"


class PurchaseOrder(models.Model):
    """Purchase order header."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted for Approval"
        APPROVED = "approved", "Approved"
        SENT = "sent", "Sent to Supplier"
        PARTIAL = "partial", "Partially Received"
        RECEIVED = "received", "Fully Received"
        CANCELLED = "cancelled", "Cancelled"
        CLOSED = "closed", "Closed"

    class PaymentStatus(models.TextChoices):
        NOT_BILLED = "not_billed", "Not Billed"
        UNPAID = "unpaid", "Unpaid"
        PARTIAL = "partial", "Partially Paid"
        PAID = "paid", "Paid"
        OVERDUE = "overdue", "Overdue"

    po_number = models.CharField(max_length=40, unique=True)
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="purchase_orders",
    )

    order_date = models.DateField(default=timezone.localdate)
    expected_delivery_date = models.DateField(null=True, blank=True)
    validity_date = models.DateField(null=True, blank=True)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.NOT_BILLED,
    )

    # Snapshot the supplier address at the time of ordering.
    billing_address = models.TextField(blank=True)
    shipping_address = models.TextField(blank=True)
    shipping_city = models.CharField(max_length=100, blank=True)
    shipping_state = models.CharField(max_length=100, blank=True)
    shipping_postal_code = models.CharField(max_length=10, blank=True)

    currency = models.CharField(max_length=3, default="INR")
    exchange_rate = models.DecimalField(
        max_digits=12, decimal_places=6, default=Decimal("1.000000")
    )

    destination_warehouse = models.CharField(max_length=150, blank=True)
    delivery_method = models.CharField(max_length=100, blank=True)
    incoterm = models.CharField(max_length=30, blank=True)
    reference_number = models.CharField(max_length=100, blank=True)

    # Tax treatment.
    place_of_supply = models.CharField(max_length=100, blank=True)
    is_interstate = models.BooleanField(default=False)
    prices_include_tax = models.BooleanField(default=False)

    discount_type = models.CharField(
        max_length=10,
        choices=[("fixed", "Fixed Amount"), ("percent", "Percentage")],
        default="fixed",
    )
    discount_value = models.DecimalField(
        max_digits=12, decimal_places=2, default=ZERO
    )

    shipping_cost = models.DecimalField(
        max_digits=12, decimal_places=2, default=ZERO
    )
    other_charges = models.DecimalField(
        max_digits=12, decimal_places=2, default=ZERO
    )
    adjustment_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=ZERO
    )

    # Persisted totals: recalculate from the lines on the server.
    subtotal = models.DecimalField(
        max_digits=14, decimal_places=2, default=ZERO
    )
    discount_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=ZERO
    )
    taxable_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=ZERO
    )
    cgst_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=ZERO
    )
    sgst_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=ZERO
    )
    igst_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=ZERO
    )
    total_tax = models.DecimalField(
        max_digits=14, decimal_places=2, default=ZERO
    )
    grand_total = models.DecimalField(
        max_digits=14, decimal_places=2, default=ZERO
    )

    terms_and_conditions = models.TextField(blank=True)
    internal_notes = models.TextField(blank=True)
    supplier_notes = models.TextField(blank=True)

    created_by = models.CharField(max_length=150, blank=True)
    approved_by = models.CharField(max_length=150, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.po_number


class PurchaseOrderLine(models.Model):
    """One product line inside a purchase order."""

    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    product = models.ForeignKey(
        "admin_panel.Product",
        on_delete=models.PROTECT,
        related_name="purchase_order_lines",
    )

    description = models.CharField(max_length=255, blank=True)
    supplier_product_code = models.CharField(max_length=100, blank=True)
    unit_of_measure = models.CharField(max_length=30, default="Units")

    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    received_quantity = models.DecimalField(
        max_digits=12, decimal_places=3, default=ZERO
    )
    billed_quantity = models.DecimalField(
        max_digits=12, decimal_places=3, default=ZERO
    )

    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(ZERO)],
    )
    discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=ZERO,
        validators=[
            MinValueValidator(ZERO),
            MaxValueValidator(Decimal("100")),
        ],
    )

    # Enter the applicable rates for this product.
    gst_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=ZERO,
        validators=[
            MinValueValidator(ZERO),
            MaxValueValidator(Decimal("100")),
        ],
    )
    cgst_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=ZERO
    )
    sgst_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=ZERO
    )
    igst_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=ZERO
    )

    line_subtotal = models.DecimalField(
        max_digits=14, decimal_places=2, default=ZERO
    )
    line_discount = models.DecimalField(
        max_digits=14, decimal_places=2, default=ZERO
    )
    taxable_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=ZERO
    )
    cgst_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=ZERO
    )
    sgst_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=ZERO
    )
    igst_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=ZERO
    )
    line_total = models.DecimalField(
        max_digits=14, decimal_places=2, default=ZERO
    )

    expected_delivery_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["id"]

    def calculate_totals(self):
        self.line_subtotal = self.quantity * self.unit_price
        self.line_discount = (
            self.line_subtotal * self.discount_percent / Decimal("100")
        )
        self.taxable_amount = self.line_subtotal - self.line_discount

        self.cgst_amount = (
            self.taxable_amount * self.cgst_rate / Decimal("100")
        )
        self.sgst_amount = (
            self.taxable_amount * self.sgst_rate / Decimal("100")
        )
        self.igst_amount = (
            self.taxable_amount * self.igst_rate / Decimal("100")
        )
        self.line_total = (
            self.taxable_amount
            + self.cgst_amount
            + self.sgst_amount
            + self.igst_amount
        )

    def save(self, *args, **kwargs):
        self.calculate_totals()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.purchase_order.po_number} - {self.product}"


class GoodsReceipt(models.Model):
    """Records an actual delivery from the supplier."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        RECEIVED = "received", "Received"
        CANCELLED = "cancelled", "Cancelled"

    receipt_number = models.CharField(max_length=40, unique=True)
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.PROTECT,
        related_name="goods_receipts",
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="goods_receipts",
    )

    receipt_date = models.DateField(default=timezone.localdate)
    supplier_delivery_note = models.CharField(max_length=100, blank=True)
    carrier_name = models.CharField(max_length=150, blank=True)
    tracking_number = models.CharField(max_length=100, blank=True)
    warehouse = models.CharField(max_length=150, blank=True)

    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    received_by = models.CharField(max_length=150, blank=True)
    inspection_notes = models.TextField(blank=True)
    internal_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-receipt_date", "-id"]

    def __str__(self):
        return self.receipt_number


class GoodsReceiptLine(models.Model):
    """Quantities received for individual purchase-order lines."""

    receipt = models.ForeignKey(
        GoodsReceipt,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    purchase_order_line = models.ForeignKey(
        PurchaseOrderLine,
        on_delete=models.PROTECT,
        related_name="receipt_lines",
    )

    quantity_received = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    quantity_accepted = models.DecimalField(
        max_digits=12, decimal_places=3, default=ZERO
    )
    quantity_rejected = models.DecimalField(
        max_digits=12, decimal_places=3, default=ZERO
    )
    rejection_reason = models.TextField(blank=True)
    batch_number = models.CharField(max_length=100, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.receipt.receipt_number} - {self.purchase_order_line}"


class VendorBill(models.Model):
    """Supplier invoice / accounts payable record."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        POSTED = "posted", "Posted"
        PARTIAL = "partial", "Partially Paid"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"

    bill_number = models.CharField(max_length=40, unique=True)
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="vendor_bills",
    )
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.PROTECT,
        related_name="vendor_bills",
        null=True,
        blank=True,
    )

    supplier_invoice_number = models.CharField(max_length=100)
    invoice_date = models.DateField(default=timezone.localdate)
    accounting_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(null=True, blank=True)

    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    currency = models.CharField(max_length=3, default="INR")
    subtotal = models.DecimalField(
        max_digits=14, decimal_places=2, default=ZERO
    )
    discount_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=ZERO
    )
    taxable_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=ZERO
    )
    cgst_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=ZERO
    )
    sgst_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=ZERO
    )
    igst_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=ZERO
    )
    other_charges = models.DecimalField(
        max_digits=14, decimal_places=2, default=ZERO
    )
    grand_total = models.DecimalField(
        max_digits=14, decimal_places=2, default=ZERO
    )
    amount_paid = models.DecimalField(
        max_digits=14, decimal_places=2, default=ZERO
    )
    amount_due = models.DecimalField(
        max_digits=14, decimal_places=2, default=ZERO
    )

    attachment = models.FileField(
        upload_to="purchases/vendor_bills/",
        null=True,
        blank=True,
    )
    notes = models.TextField(blank=True)
    created_by = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-invoice_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["supplier", "supplier_invoice_number"],
                name="unique_supplier_invoice_number",
            )
        ]

    def __str__(self):
        return self.bill_number


class VendorBillLine(models.Model):
    """Items charged on a supplier's invoice."""

    bill = models.ForeignKey(
        VendorBill,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    product = models.ForeignKey(
        "admin_panel.Product",
        on_delete=models.PROTECT,
        related_name="vendor_bill_lines",
    )
    purchase_order_line = models.ForeignKey(
        PurchaseOrderLine,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="vendor_bill_lines",
    )

    description = models.CharField(max_length=255, blank=True)
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(ZERO)],
    )
    discount_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=ZERO
    )
    taxable_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=ZERO
    )
    cgst_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=ZERO
    )
    sgst_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=ZERO
    )
    igst_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=ZERO
    )
    line_total = models.DecimalField(
        max_digits=14, decimal_places=2, default=ZERO
    )

    def __str__(self):
        return f"{self.bill.bill_number} - {self.product}"


class VendorPayment(models.Model):
    """Money paid to a supplier."""

    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        BANK = "bank", "Bank Transfer"
        UPI = "upi", "UPI"
        CARD = "card", "Card"
        CHEQUE = "cheque", "Cheque"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        POSTED = "posted", "Posted"
        CANCELLED = "cancelled", "Cancelled"

    payment_number = models.CharField(max_length=40, unique=True)
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    payment_date = models.DateField(default=timezone.localdate)
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    currency = models.CharField(max_length=3, default="INR")
    method = models.CharField(
        max_length=15, choices=Method.choices, default=Method.BANK
    )
    transaction_reference = models.CharField(max_length=150, blank=True)
    bank_name = models.CharField(max_length=150, blank=True)
    cheque_number = models.CharField(max_length=100, blank=True)

    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    notes = models.TextField(blank=True)
    created_by = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-payment_date", "-id"]

    def __str__(self):
        return self.payment_number


class VendorPaymentAllocation(models.Model):
    """Allows one payment to settle one or multiple vendor bills."""

    payment = models.ForeignKey(
        VendorPayment,
        on_delete=models.PROTECT,
        related_name="allocations",
    )
    bill = models.ForeignKey(
        VendorBill,
        on_delete=models.PROTECT,
        related_name="payment_allocations",
    )
    amount_allocated = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["payment", "bill"],
                name="unique_payment_bill_allocation",
            )
        ]

    def __str__(self):
        return f"{self.payment.payment_number} → {self.bill.bill_number}"