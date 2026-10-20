from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from allauth.socialaccount.models import SocialAccount
from .models import Customer


@receiver(user_logged_in)
def sync_google_customer(sender, request, user, **kwargs):
    if request is None:
        return

    google_account = SocialAccount.objects.filter(
        user=user,
        provider="google"
    ).first()

    if not google_account:
        return

    extra_data = google_account.extra_data or {}

    email = (
        extra_data.get("email")
        or user.email
        or ""
    ).strip().lower()

    if not email:
        return

    # Only register accounts whose email Google has verified.
    if extra_data.get("email_verified") is not True:
        return

    customer = Customer.objects.filter(
        email__iexact=email
    ).first()

    if not customer:
        name = (
            extra_data.get("name")
            or user.get_full_name()
            or user.username
        ).strip()

        base_username = user.username or email.split("@")[0]
        username = base_username[:100]
        counter = 1

        while Customer.objects.filter(username=username).exists():
            suffix = str(counter)
            username = base_username[:100 - len(suffix)] + suffix
            counter += 1

        customer = Customer.objects.create(
            name=name[:100],
            email=email,
            username=username,
            phone="",
            password="",
        )

        print("New UNCOMMON customer registered:", customer.id)

    request.session["customer_id"] = customer.id
    request.session.modified = True

    print("UNCOMMON customer logged in:", customer.id)