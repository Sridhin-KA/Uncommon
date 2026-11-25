from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from admin_panel.models import Product  # Adjust if Product is in another app


class StaticViewSitemap(Sitemap):
    changefreq = "weekly"
    priority = 1.0

    def items(self):
        return ["customer_home"]

    def location(self, item):
        return reverse(item)


class ProductSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return Product.objects.filter(is_archived=False)

    def location(self, obj):
        return reverse("product_detail", args=[obj.pk])

    def lastmod(self, obj):
        return obj.created_at