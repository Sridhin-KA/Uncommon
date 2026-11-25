"""
URL configuration for uncommon project.
"""

from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.http import HttpResponse
from django.urls import path, include

from admin_panel.views import admin_finance_weekly
from customer.sitemaps import StaticViewSitemap, ProductSitemap
from django.conf import settings
from django.conf.urls.static import static


def robots_txt(request):
    content = """User-agent: *
Allow: /

Disallow: /admin/
Disallow: /admin_panel/
Disallow: /login/
Disallow: /register/
Disallow: /checkout/
Disallow: /my-orders/
Disallow: /profile/
Disallow: /addresses/

Sitemap: https://uncommen.in/sitemap.xml
"""
    return HttpResponse(content, content_type="text/plain")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("admin_panel/", include("admin_panel.urls")),

    # SEO files
    path("robots.txt", robots_txt, name="robots_txt"),
    path(
        "sitemap.xml",
        sitemap,
        {
            "sitemaps": {
                "static": StaticViewSitemap,
                "products": ProductSitemap,
            }
        },
        name="django.contrib.sitemaps.views.sitemap",
    ),

    # Customer app
    path("", include("customer.urls")),
    path("accounts/", include("allauth.urls")),

    # Finance API
    path(
        "api/admin/finance/weekly/",
        admin_finance_weekly,
        name="admin_finance_weekly",
    ),
]

urlpatterns += static(
    settings.MEDIA_URL,
    document_root=settings.MEDIA_ROOT,
)