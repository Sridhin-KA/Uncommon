import base64
import requests

from django.conf import settings


def _send_brevo_email(to_email, subject, text, attachments=None):
    """
    Send an email through the Brevo HTTPS API.

    attachments: optional list of dictionaries:
        [{"name": "invoice.pdf", "content": pdf_bytes}]
    """
    api_key = settings.BREVO_API_KEY
    sender_email = settings.BREVO_SENDER_EMAIL

    if not api_key or not sender_email:
        raise ValueError(
            "Brevo API key or sender email is not configured."
        )

    if not to_email:
        raise ValueError("Recipient email address is missing.")

    payload = {
        "sender": {
            "name": "UNCOMMEN Team",
            "email": sender_email,
        },
        "to": [{"email": to_email}],
        "subject": subject,
        "textContent": text,
    }

    if attachments:
        payload["attachment"] = [
            {
                "name": attachment["name"],
                "content": base64.b64encode(
                    attachment["content"]
                ).decode("ascii"),
            }
            for attachment in attachments
        ]

    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "accept": "application/json",
                "api-key": api_key,
                "content-type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        response.raise_for_status()

    except requests.RequestException as exc:
        response_text = (
            exc.response.text
            if exc.response is not None
            else "No response received from Brevo."
        )

        raise RuntimeError(
            f"Brevo email request failed: {response_text}"
        ) from exc

    return response.json()