from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.shortcuts import resolve_url
from .models import Customer


class CustomAccountAdapter(DefaultAccountAdapter):
    def get_login_redirect_url(self, request):
        return resolve_url("/")


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)

        email = (
            sociallogin.user.email
            or sociallogin.account.extra_data.get("email")
            or ""
        ).strip()

        if not email:
            return user

        customer = Customer.objects.filter(
            email__iexact=email
        ).first()

        if customer:
            request.session["customer_id"] = customer.id
            request.session.modified = True

        return user