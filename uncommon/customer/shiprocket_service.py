import requests

from django.conf import settings
from django.core.cache import cache

SHIPROCKET_BASE_URL = "https://apiv2.shiprocket.in/v1/external"

TOKEN_CACHE_KEY = "shiprocket_api_token"
TOKEN_CACHE_TIMEOUT = 9 * 24 * 60 * 60


def generate_shiprocket_token():
    email = settings.SHIPROCKET_EMAIL
    password = settings.SHIPROCKET_PASSWORD

    if not email or not password:
        raise ValueError("Shiprocket credentials are missing.")

    response = requests.post(
        f"{SHIPROCKET_BASE_URL}/auth/login",
        json={
            "email": email,
            "password": password,
        },
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()
    token = data.get("token")

    if not token:
        raise ValueError("Shiprocket token not received.")

    cache.set(
        TOKEN_CACHE_KEY,
        token,
        TOKEN_CACHE_TIMEOUT
    )

    return token


def get_shiprocket_token():
    token = cache.get(TOKEN_CACHE_KEY)

    if token:
        return token

    return generate_shiprocket_token()


def shiprocket_request(method, endpoint, **kwargs):
    token = get_shiprocket_token()

    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {token}"

    url = f"{SHIPROCKET_BASE_URL}/{endpoint.lstrip('/')}"

    response = requests.request(
        method,
        url,
        headers=headers,
        timeout=30,
        **kwargs,
    )

    if response.status_code == 401:
        cache.delete(TOKEN_CACHE_KEY)

        token = generate_shiprocket_token()
        headers["Authorization"] = f"Bearer {token}"

        response = requests.request(
            method,
            url,
            headers=headers,
            timeout=30,
            **kwargs,
        )

    response.raise_for_status()

    return response.json()