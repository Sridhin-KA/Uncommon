"""
URL configuration for uncommon project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path,include
from admin_panel.views import *
from django.views.generic import TemplateView
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from customer.sitemaps import StaticViewSitemap, ProductSitemap
urlpatterns = [
    path('admin/', admin.site.urls),
    path('admin_panel/',include('admin_panel.urls')),
    path('', include('customer.urls')),
    path("accounts/", include("allauth.urls")),
    path(
        "api/admin/finance/weekly/",
        admin_finance_weekly,
        name="admin_finance_weekly",
    ),
     path(
        "robots.txt",
        TemplateView.as_view(
            template_name="robots.txt",
            content_type="text/plain"
        ),
    ),
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
]
urlpatterns += static(
    settings.MEDIA_URL,
    document_root=settings.MEDIA_ROOT
)