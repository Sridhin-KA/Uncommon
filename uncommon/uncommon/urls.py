"""
URL configuration for uncommon project.
"""
from pathlib import Path
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.http import HttpResponse
from django.urls import path, include
from django.http import FileResponse, Http404
from admin_panel.views import admin_finance_weekly
from customer.sitemaps import StaticViewSitemap, ProductSitemap
from django.conf import settings
from django.conf.urls.static import static

def google_site_verification(request):
    file_path = (
        Path(settings.BASE_DIR)
        / "static"
        / "google3a6b2baeda5b2d74.html"
    )

    if not file_path.is_file():
        raise Http404("Google verification file not found")

    return FileResponse(
        open(file_path, "rb"),
        content_type="text/html",
    )

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
    path(
    "google3a6b2baeda5b2d74.html",
    google_site_verification,
    name="google_site_verification",
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