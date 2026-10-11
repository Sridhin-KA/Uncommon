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