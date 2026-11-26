from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from pathlib import Path
import logging
import re

import fitz
from django.conf import settings
from django.core.files.base import ContentFile
from customer.services.brevo import _send_brevo_email
from django.db import transaction
from django.utils import timezone

from customer.models import Order, OrderItem, TaxInvoice

logger = logging.getLogger(__name__)
CENT = Decimal("0.01")
ZERO = Decimal("0.00")
SELLER_STATE = getattr(settings, "INVOICE_SELLER_STATE", "Karnataka")
SELLER_STATE_CODE = getattr(settings, "INVOICE_SELLER_STATE_CODE", "29")
TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "templates" / "uncommen_invoice_template.pdf"


def money(value):
    return Decimal(value or 0).quantize(CENT, rounding=ROUND_HALF_UP)


def inr_words(amount):
    # Indian numbering system; suitable for invoice totals.
    n = int(money(amount))
    paise = int((money(amount) - int(money(amount))) * 100)
    ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
            "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
            "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

    def under_thousand(x):
        out = []
        if x >= 100:
            out += [ones[x // 100], "Hundred"]
            x %= 100
        if x >= 20:
            out.append(tens[x // 10])
            if x % 10:
                out.append(ones[x % 10])
        elif x:
            out.append(ones[x])
        return " ".join(out)

    def indian(x):
        if x == 0:
            return "Zero"
        parts = []
        for divisor, label in [(10000000, "Crore"), (100000, "Lakh"), (1000, "Thousand"), (1, "")]:
            q, x = divmod(x, divisor)
            if q:
                parts.append((under_thousand(q) + " " + label).strip())
        return " ".join(parts)

    result = indian(n) + " Rupees"
    if paise:
        result += " and " + under_thousand(paise) + " Paise"
    return result + " Only"


def parse_address(order):
    raw = (order.shipping_address or "").splitlines()
    recipient = raw[0].strip() if raw else order.customer.name
    phone = raw[1].strip() if len(raw) > 1 else (order.customer.phone or "")
    address = raw[2].strip() if len(raw) > 2 else ""
    locality = raw[3].strip() if len(raw) > 3 else ""
    state = ""
    pin = ""
    match = re.search(r",\s*(.*?)\s*-\s*(\d{6})$", locality)
    if match:
        state, pin = match.group(1).strip(), match.group(2)
    elif locality:
        state = locality
    full = ", ".join(x for x in [address, locality] if x)
    return {
        "recipient": recipient, "phone": phone, "address": full,
        "state": state, "pin": pin,
    }


def line_tax(item, state):
    gross = money(item.price * item.quantity)
    rate = item.product.gst_rate
    if rate is None:
        raise ValueError(
            f"GST rate is missing for product '{item.product.product_name}'. "
            "Set Product.gst_rate before issuing a tax invoice."
        )
    rate = Decimal(str(rate))
    taxable = money(gross / (Decimal("1") + rate / Decimal("100")))
    tax = money(gross - taxable)
    intra = bool(state) and state.casefold() == SELLER_STATE.casefold()
    return {
        "gross": gross, "taxable": taxable, "rate": rate, "tax": tax,
        "cgst": money(tax / 2) if intra else ZERO,
        "sgst": money(tax - money(tax / 2)) if intra else ZERO,
        "igst": ZERO if intra else tax,
        "hsn": item.product.hsn_code or "",
        "name": item.product.product_name,
        "qty": item.quantity,
    }


def put_text(page, rect, value, *, size=7.4, align=0, color=(0.12, 0.12, 0.12)):
    # White out placeholder/content, then insert fitted replacement text.
    page.draw_rect(rect, color=None, fill=(1, 1, 1), overlay=True)
    page.insert_textbox(
        rect, str(value or "—"), fontsize=size, fontname="helv",
        color=color, align=align, overlay=True
    )


def create_invoice_pdf(order, invoice):
    items = list(
        OrderItem.objects.filter(order=order)
        .select_related("product").order_by("id")
    )
    address = parse_address(order)
    state = address["state"]
    if not state:
        raise ValueError("Delivery state is missing; cannot determine GST place of supply.")

    tax_lines = [line_tax(item, state) for item in items]
    gross = sum((x["gross"] for x in tax_lines), ZERO)
    taxable = sum((x["taxable"] for x in tax_lines), ZERO)
    cgst = sum((x["cgst"] for x in tax_lines), ZERO)
    sgst = sum((x["sgst"] for x in tax_lines), ZERO)
    igst = sum((x["igst"] for x in tax_lines), ZERO)
    if money(gross) != money(order.total_amount):
        raise ValueError("Invoice item total does not match the saved order total.")

    doc = fitz.open(TEMPLATE_PATH)
    p1, p2 = doc[0], doc[1]
    now = timezone.localtime(invoice.created_at or timezone.now())
    paid = order.payment_status == "PAID"
    payment_mode = "PREPAID — PAID" if paid else "COD — PAYMENT DUE"
    payment_ref = ""
    if paid:
        payment = order.payments.filter(status="PAID").order_by("-updated_at").first()
        payment_ref = payment.razorpay_payment_id if payment else "Razorpay"
    else:
        payment_ref = "Payable on delivery"

    # Page 1: header and invoice details (fixed template coordinates).
    put_text(p1, fitz.Rect(365, 94, 470, 111), order.order_number, size=7.0)
    put_text(p1, fitz.Rect(470, 94, 550, 111), payment_mode, size=6.2)
    values = [
        (fitz.Rect(385, 153, 555, 170), invoice.invoice_number),
        (fitz.Rect(385, 169, 555, 186), now.strftime("%d-%b-%Y")),
        (fitz.Rect(385, 185, 555, 202), timezone.localtime(order.created_at).strftime("%d-%b-%Y")),
        (fitz.Rect(385, 201, 555, 218), f"{state}"),
        (fitz.Rect(385, 217, 555, 234), "INTRA-STATE" if state.casefold() == SELLER_STATE.casefold() else "INTER-STATE"),
        (fitz.Rect(385, 232, 555, 249), payment_ref),
        (fitz.Rect(130, 337, 285, 354), order.customer.name),
        (fitz.Rect(130, 352, 285, 369), order.customer.phone),
        (fitz.Rect(130, 368, 285, 385), order.customer.email),
        (fitz.Rect(130, 383, 285, 401), address["address"]),
        (fitz.Rect(130, 399, 285, 416), state),
        (fitz.Rect(385, 337, 555, 354), address["recipient"]),
        (fitz.Rect(385, 352, 555, 369), address["phone"]),
        (fitz.Rect(385, 368, 555, 385), address["address"]),
        (fitz.Rect(385, 383, 555, 401), state),
        (fitz.Rect(385, 399, 555, 416), "—"),
    ]
    for rect, val in values:
        put_text(p1, rect, val, size=6.4)

    # Remove the sample product row and fill actual rows. If necessary,
    # extra items are continued on additional branded invoice pages below.
    p1.draw_rect(fitz.Rect(48, 458, 555, 515), color=None, fill=(1, 1, 1), overlay=True)
    row_y = 464
    row_h = 13
    for idx, line in enumerate(tax_lines[:3], 1):
        y = row_y + (idx - 1) * row_h
        put_text(p1, fitz.Rect(50, y, 70, y + 12), str(idx), size=6.8)
        put_text(p1, fitz.Rect(78, y, 365, y + 12), line["name"], size=6.5)
        put_text(p1, fitz.Rect(365, y, 395, y + 12), str(line["qty"]), size=6.5, align=1)
        put_text(p1, fitz.Rect(395, y, 443, y + 12), f"{line['taxable']:.2f}", size=6.3, align=2)
        put_text(p1, fitz.Rect(444, y, 485, y + 12), f"{line['rate']}%", size=6.3, align=2)
        put_text(p1, fitz.Rect(486, y, 550, y + 12), f"{line['gross']:.2f}", size=6.3, align=2)

    put_text(p1, fitz.Rect(52, 519, 540, 540), inr_words(gross), size=7.0)
    for rect, val in [
        (fitz.Rect(330, 549, 555, 567), f"₹ {gross:.2f}"),
        (fitz.Rect(330, 568, 555, 585), f"₹ {taxable:.2f}"),
        (fitz.Rect(330, 586, 555, 604), f"₹ {cgst:.2f}"),
        (fitz.Rect(330, 605, 555, 622), f"₹ {sgst:.2f}"),
        (fitz.Rect(330, 624, 555, 641), f"₹ {igst:.2f}"),
        (fitz.Rect(330, 643, 555, 662), f"₹ {gross:.2f}" if paid else f"₹ {gross:.2f} (DUE)"),
    ]:
        put_text(p1, rect, val, size=7.2, align=2)

    # COD and prepaid payment status must remain explicit on page 2 as well.
    put_text(p2, fitz.Rect(380, 137, 555, 155), order.order_number, size=7.2)
    put_text(p2, fitz.Rect(380, 153, 555, 171), invoice.invoice_number, size=7.2)
    put_text(p2, fitz.Rect(380, 181, 555, 199), now.strftime("%d-%b-%Y"), size=7.2)

    # More than three product lines: add continuation sheet(s), never drop lines.
    if len(tax_lines) > 3:
        remaining = tax_lines[3:]
        for chunk_no in range(0, len(remaining), 32):
            page = doc.new_page(width=p1.rect.width, height=p1.rect.height)
            page.insert_text((42, 48), "UNCOMMEN — TAX INVOICE (CONTINUED)", fontsize=15, fontname="helv", color=(0.08, 0.08, 0.08))
            page.insert_text((42, 70), f"Invoice: {invoice.invoice_number}    Order: {order.order_number}", fontsize=8)
            page.draw_line((42, 82), (553, 82), color=(0.3, 0.3, 0.3), width=0.7)
            headers = [("#", 42, 65), ("PRODUCT", 70, 315), ("QTY", 320, 355), ("TAXABLE", 360, 425), ("GST", 430, 475), ("TOTAL", 480, 553)]
            for label, x0, x1 in headers:
                page.insert_textbox(fitz.Rect(x0, 94, x1, 108), label, fontsize=7, fontname="hebo")
            for j, line in enumerate(remaining[chunk_no:chunk_no + 32]):
                y = 112 + j * 19
                vals = [
                    (42, 65, str(chunk_no + j + 4), 6.5),
                    (70, 315, line["name"], 6.5),
                    (320, 355, str(line["qty"]), 6.5),
                    (360, 425, f"{line['taxable']:.2f}", 6.5),
                    (430, 475, f"{line['rate']}%", 6.5),
                    (480, 553, f"{line['gross']:.2f}", 6.5),
                ]
                for x0, x1, val, fs in vals:
                    page.insert_textbox(fitz.Rect(x0, y, x1, y + 15), val, fontsize=fs, fontname="helv")
                page.draw_line((42, y + 16), (553, y + 16), color=(0.85, 0.85, 0.85), width=0.3)
            page.insert_text((42, 790), f"Continued invoice items — {invoice.invoice_number}", fontsize=7)

    # Stamp page footer labels after inserted continuation pages.
    for idx, page in enumerate(doc):
        page.search_for("Page 1 of 2")
        # Template page numbers are retained on the original artwork; overlay
        # a small dynamic page count in the bottom-right safe margin.
        page.insert_text((530, 824), f"{idx + 1}/{len(doc)}", fontsize=6, color=(0.35, 0.35, 0.35))

    return doc.tobytes(deflate=True, garbage=4)

def issue_and_email_invoice(order_id):
    """
    Idempotent invoice issuance.

    Prepaid orders should call this only after confirmed Razorpay capture.
    COD orders may call it once the COD order is placed.
    """
    with transaction.atomic():
        order = (
            Order.objects
            .select_for_update()
            .select_related("customer")
            .get(pk=order_id)
        )

        if (
            order.payment_method == "PREPAID"
            and order.payment_status != "PAID"
        ):
            return None

        invoice, created = TaxInvoice.objects.get_or_create(
            order=order,
            defaults={
                "invoice_number": (
                    f"UN-TAX-{timezone.localdate():%Y%m}-{order.pk:06d}"
                )
            },
        )

        if invoice.email_sent_at:
            return invoice

        # Generate the PDF bytes for this email attempt.
        # This avoids reopening a possibly private Cloudinary file.
        pdf_bytes = create_invoice_pdf(order, invoice)

        # Save the PDF if it has not already been saved.
        if not invoice.pdf:
            invoice.pdf.save(
                f"{invoice.invoice_number}.pdf",
                ContentFile(pdf_bytes),
                save=True,
            )

    # Send outside the database transaction.
    # If Brevo fails, the invoice remains saved and can be retried.
    subject = (
        f"Your UNCOMMEN tax invoice — {invoice.invoice_number}"
    )

    body = (
        f"Hello {order.customer.name},\n\n"
        "Thank you for shopping with UNCOMMEN.\n"
        "Please find your tax invoice attached.\n\n"
        f"Order: {order.order_number}\n"
        f"Invoice: {invoice.invoice_number}\n"
        f"Payment status: "
        f"{'PAID' if order.payment_status == 'PAID' else 'PAYMENT DUE — COD'}\n\n"
        "For assistance, contact contact@uncommen.in.\n\n"
        "UNCOMMEN — The House"
    )

    try:
        _send_brevo_email(
            to_email=order.customer.email,
            subject=subject,
            text=body,
            attachments=[
                {
                    "name": f"{invoice.invoice_number}.pdf",
                    "content": pdf_bytes,
                }
            ],
        )

    except Exception:
        logger.exception(
            "Invoice %s was generated but Brevo email delivery failed.",
            invoice.invoice_number,
        )
        return invoice

    invoice.email_sent_at = timezone.now()
    invoice.save(update_fields=["email_sent_at"])

    return invoice