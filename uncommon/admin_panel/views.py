"""
UNCOMMON Admin Panel Views

Sections
    1. Imports, constants and decorators
    2. Auth (login / logout / finance password)
    3. Dashboard
    4. Financial and GST reports
    5. Categories
    6. Products
    7. Customers
    8. Orders (+ status emails)
    9. Feedback
   10. Purchasing (suppliers, POs, goods receipts, vendor bills, payments)
"""
from django.urls import reverse
import csv
from customer.views import get_razorpay_client
import re
import json
import logging
import secrets
from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from functools import wraps
from django.views.decorators.http import require_http_methods
import requests
from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, Prefetch, Q, Sum
from django.db.models.deletion import ProtectedError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.db.models import Avg, Count
from customer.views import get_logged_in_customer
from customer.models import *  # noqa: F401,F403  (Customer, Order, OrderItem, Payment, Feedback, ...)
from .models import *  # noqa: F401,F403  (Admin, Category, Product, Supplier, PurchaseOrder, ...)
from customer.services.brevo import _send_brevo_email
logger = logging.getLogger(__name__)


# =============================================================================
# 1. CONSTANTS AND DECORATORS
# =============================================================================

ZERO = Decimal("0.00")
CENT = Decimal("0.01")

# Optional settings.py values
BUSINESS_STATE = getattr(settings, "BUSINESS_STATE", "Kerala")
PRICES_INCLUDE_GST = getattr(settings, "GST_PRICES_INCLUDE_TAX", True)
B2CL_LIMIT = Decimal(str(getattr(settings, "GST_B2CL_THRESHOLD", 100000)))  # confirm with your accountant
CANCELLED = {"CANCELLED", "RETURNED", "RTO", "REFUNDED"}  # paid orders in these statuses get a credit note

FINANCE_ACCESS_SECONDS = 15 * 60

ORDER_STATUSES = ["PENDING", "CONFIRMED", "SHIPPED", "DELIVERED", "CANCELLED"]

ORDER_STATUS_EMAILS = {
    "PENDING": (
        "Your order is pending.",
        "We have received your order and it is awaiting confirmation.",
    ),
    "CONFIRMED": (
        "Your order has been confirmed!",
        "Great news! Your order has been confirmed and is being prepared.",
    ),
    "SHIPPED": (
        "Your order has been shipped!",
        "Your order is on its way. We will keep you updated.",
    ),
    "DELIVERED": (
        "Your order has been delivered!",
        "Your order has been marked as delivered. We hope you love your purchase!",
    ),
    "CANCELLED": (
        "Your order has been cancelled.",
        "Your order has been cancelled. Please contact us if you need assistance.",
    ),
}


def is_ajax(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def admin_required(view):
    """Require a valid admin session. Sets request.admin_user."""
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        admin_id = request.session.get("admin")
        admin = Admin.objects.filter(pk=admin_id).first() if admin_id else None
        if admin is None:
            if admin_id:
                request.session.flush()
            return redirect("home")
        request.admin_user = admin
        return view(request, *args, **kwargs)
    return wrapped


def has_finance_access(request):
    """True when an admin is logged in and the finance password was verified recently."""
    if not request.session.get("admin"):
        return False
    try:
        until = float(request.session.get("finance_access_until") or 0)
    except (TypeError, ValueError):
        until = 0
    return bool(until) and timezone.now().timestamp() < until


def finance_required(view):
    """Require an admin session AND a recently verified finance password."""
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.session.get("admin"):
            if is_ajax(request):
                return JsonResponse({"success": False, "message": "Admin login required."}, status=401)
            messages.error(request, "Please log in as admin.")
            return redirect("home")

        if not has_finance_access(request):
            request.session.pop("finance_access_until", None)
            if is_ajax(request):
                return JsonResponse(
                    {"success": False, "message": "Finance password verification required."}, status=403
                )
            messages.error(request, "Finance access expired. Verify your finance password again.")
            return redirect("admin_index")

        return view(request, *args, **kwargs)
    return wrapped


# Old name kept so any existing import or urls.py reference keeps working.
finance_password_required = finance_required


def _paginate(request, queryset, per_page):
    return Paginator(queryset, per_page).get_page(request.GET.get("page"))


# =============================================================================
# 2. AUTH
# =============================================================================

def home(request):
    return render(request, "admin_panel/auth_page.html")


def login(request):
    if request.method != "POST":
        return render(request, "admin_panel/auth_page.html")

    email = request.POST.get("email", "").strip()
    password = request.POST.get("password", "")

    # Save guest bag and intended destination before the session is flushed.
    guest_bag = request.session.get("bag", {})
    next_page = request.session.get("next_after_login", "customer_home")

    # 1. Admin
    admin = Admin.objects.filter(email=email).first()
    if admin and admin.password == password:
        request.session.flush()
        request.session["admin"] = admin.id
        return redirect("admin_index")

    # 2. Customer
    customer = Customer.objects.filter(email=email).first()
    if customer and customer.password == password:
        request.session.flush()
        request.session["customer_id"] = customer.id
        request.session["bag"] = guest_bag
        return redirect("checkout" if next_page == "checkout" else "customer_home")

    # 3. Invalid credentials
    return render(request, "admin_panel/auth_page.html", {"error": "Invalid email or password"})


@require_http_methods(["GET", "POST"])
def admin_login(request):

    # Already authenticated
    if request.session.get("admin"):
        return redirect("admin_index")

    if request.method == "POST":

        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")

        admin = Admin.objects.filter(email=email).first()

        if admin and admin.password == password:

            # Prevent session fixation
            request.session.cycle_key()

            # Store admin session
            request.session["admin"] = admin.id

            return redirect("admin_index")

        return render(
            request,
            "admin_panel/admin_login.html",
            {
                "error": "Invalid administrator email or password."
            }
        )

    return render(
        request,
        "admin_panel/admin_login.html"
    )

def customer_login(request):
    if request.method != "POST":
        return render(request, "admin_panel/auth_page.html")

    email = request.POST.get("email", "").strip()
    password = request.POST.get("password", "")

    # Preserve guest bag and intended destination
    guest_bag = request.session.get("bag", {})
    next_page = request.session.get("next_after_login", "customer_home")

    customer = Customer.objects.filter(email=email).first()

    if customer and customer.password == password:
        request.session.flush()

        request.session["customer_id"] = customer.id
        request.session["bag"] = guest_bag

        return redirect(
            "checkout" if next_page == "checkout" else "customer_home"
        )

    return render(
        request,
        "admin_panel/auth_page.html",
        {"error": "Invalid email or password"}
    )

def admin_logout(request):
    for key in ("admin", "customer_id", "finance_access_until"):
        request.session.pop(key, None)
    return redirect("uncommen/")


@require_POST
def verify_finance_password(request):
    """Grant 15 minutes of finance access after the correct password is entered."""
    if not request.session.get("admin"):
        return JsonResponse({"success": False, "message": "Admin login required."}, status=401)

    try:
        if "application/json" in (request.content_type or ""):
            body = json.loads(request.body.decode("utf-8") or "{}")
            entered = str(body.get("password", ""))
        else:
            entered = request.POST.get("password", "")
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
        return JsonResponse({"success": False, "message": "Invalid request data."}, status=400)

    correct = getattr(settings, "FINANCE_ACCESS_PASSWORD", "")
    if not correct:
        return JsonResponse({"success": False, "message": "Finance password is not configured."}, status=503)

    # Compare as bytes so non-ASCII passwords cannot raise TypeError.
    if not entered or not secrets.compare_digest(entered.encode("utf-8"), str(correct).encode("utf-8")):
        return JsonResponse({"success": False, "message": "Incorrect password."}, status=403)

    request.session["finance_access_until"] = timezone.now().timestamp() + FINANCE_ACCESS_SECONDS
    return JsonResponse({"success": True, "message": "Password verified successfully."})


# =============================================================================
# 3. DASHBOARD
# =============================================================================

@admin_required
def admin_index(request):
    context = {
        "admin": request.admin_user,
        "total_products": Product.objects.count(),
        "total_categories": Category.objects.count(),
        "total_customers": Customer.objects.count(),
        "total_orders": Order.objects.count(),
        "active_orders": Order.objects.exclude(status__in=["DELIVERED", "CANCELLED"]).count(),
        "total_feedback": 0,
        "recent_products": Product.objects.select_related("category").order_by("-id")[:5],
        "recent_orders": Order.objects.select_related("customer").order_by("-created_at")[:5],
        "recent_order_items": (
            OrderItem.objects
            .select_related("product", "product__category", "order", "order__customer")
            .order_by("-id")[:10]
        ),
    }

    # Purchasing data used by the dashboard modals:
    # suppliers, purchase_orders, goods_receipts, vendor_bills, vendor_payments,
    # procurement_products, procurement_categories, procurement_po_lines, procurement_bills
    context.update(purchasing_dashboard_context())

    return render(request, "admin_panel/index.html", context)

# =============================================================================
# 4. FINANCIAL AND GST REPORTS
# =============================================================================

def _admin_or_401(request):
    """None when the admin session is valid, otherwise a 401 JSON response."""
    admin_id = request.session.get("admin")
    if admin_id:
        if Admin.objects.filter(pk=admin_id).exists():
            return None
        request.session.flush()
    return JsonResponse({"detail": "Authentication required."}, status=401)


def _first_field(model, names):
    have = {f.name for f in model._meta.concrete_fields}
    return next((n for n in names if n in have), None)


def _ctx():
    """Which optional columns your database actually has. A missing column means 'not recorded'."""
    return {
        "cost": _first_field(Product, ("cost_price", "purchase_price", "unit_cost", "buying_price")),
        "rate": _first_field(Product, ("gst_rate", "gst_percent", "gst_percentage", "tax_rate")),
        "hsn": _first_field(Product, ("hsn_code", "hsn")),
        "state_order": _first_field(Order, ("shipping_state", "delivery_state", "state")),
        "state_customer": _first_field(Customer, ("state", "shipping_state")),
        "gstin": _first_field(Customer, ("gstin", "gst_number", "gst_no")),
    }


def _local_date(dt):
    return (timezone.localtime(dt) if timezone.is_aware(dt) else dt).date()


def _paid_orders(start_dt, end_dt):
    """Orders created in [start_dt, end_dt) that have at least one Payment with status PAID."""
    return (
        Order.objects
        .filter(created_at__gte=start_dt, created_at__lt=end_dt, payments__status="PAID")
        .distinct()
        .select_related("customer")
        .prefetch_related(Prefetch("items", queryset=OrderItem.objects.select_related("product")), "payments")
        .order_by("created_at")
    )


def _state(order, ctx):
    value = getattr(order, ctx["state_order"], "") if ctx["state_order"] else ""
    if not value and ctx["state_customer"] and order.customer:
        value = getattr(order.customer, ctx["state_customer"], "")
    return (value or "").strip()


def _line(order, item, ctx):
    """One order line with its tax. tax is None when the product has no recorded GST rate."""
    amount = Decimal(item.price) * item.quantity
    rate = getattr(item.product, ctx["rate"], None) if ctx["rate"] else None
    out = {
        "amount": amount, "rate": None, "taxable": amount, "tax": None, "split": None,
        "hsn": (getattr(item.product, ctx["hsn"], "") or "") if ctx["hsn"] else "",
    }
    if rate is None:
        return out

    r = Decimal(str(rate))
    r = r / 100 if r > 1 else r
    if PRICES_INCLUDE_GST:
        taxable = amount / (1 + r)
        tax = amount - taxable
    else:
        taxable, tax = amount, amount * r

    state = _state(order, ctx)
    if state:
        intra = state.lower() == BUSINESS_STATE.strip().lower()
        split = (
            {"cgst": tax / 2, "sgst": tax / 2, "igst": ZERO} if intra
            else {"cgst": ZERO, "sgst": ZERO, "igst": tax}
        )
    else:
        split = {"cgst": ZERO, "sgst": ZERO, "igst": ZERO, "unsplit": tax}

    out.update(rate=r, taxable=taxable, tax=tax, split=split)
    return out


def _f(x):
    return round(float(x), 2)


def admin_finance_weekly(request):
    """
    Weekly finance data for the Financial Report (last 52 weeks).
    Counts an order only when it has a Payment with status PAID.
    Anything the database does not record stays at zero and is listed under recorded_fields.
    """
    denied = _admin_or_401(request)
    if denied:
        return denied

    tz = timezone.get_current_timezone()
    today = timezone.localdate()
    this_monday = today - timedelta(days=today.weekday())
    first_monday = this_monday - timedelta(weeks=51)
    start_dt = timezone.make_aware(datetime.combine(first_monday, time.min), tz)
    end_dt = timezone.make_aware(datetime.combine(this_monday + timedelta(weeks=1), time.min), tz)

    keys = ["orders", "gross", "checkoutAddons", "discounts", "returns", "rtoOrders", "rtoRev", "cogs",
            "shipping", "fees", "ads", "rtoCost", "fixed", "codOrders", "s5", "s18", "intra",
            "itcG", "itcS", "itcF", "itcA", "itcO"]
    buckets = {}
    for offset in range(52):
        ws = first_monday + timedelta(weeks=offset)
        buckets[ws.isoformat()] = {"start": ws.isoformat(), **{k: 0.0 for k in keys}}

    ctx = _ctx()
    for order in _paid_orders(start_dt, end_dt):
        d = _local_date(order.created_at)
        bucket = buckets.get((d - timedelta(days=d.weekday())).isoformat())
        if bucket is None:
            continue

        items = list(order.items.all())
        lines = [_line(order, it, ctx) for it in items]
        item_sales = sum((l["amount"] for l in lines), ZERO)
        taxable_sum = sum((l["taxable"] for l in lines), ZERO)
        cancelled = (order.status or "").upper() in CANCELLED

        bucket["orders"] += 1
        bucket["gross"] += _f(taxable_sum)
        bucket["checkoutAddons"] += _f(max((order.total_amount or ZERO) - item_sales, ZERO))
        if cancelled:
            bucket["returns"] += _f(taxable_sum)
            continue

        for l, it in zip(lines, items):
            if ctx["cost"]:
                cost = getattr(it.product, ctx["cost"], None)
                if cost is not None:
                    bucket["cogs"] += _f(Decimal(str(cost)) * it.quantity)
            if l["rate"] is not None:
                bucket["s5" if l["rate"] == Decimal("0.05") else "s18"] += _f(l["taxable"])
                if l["split"] and (l["split"]["cgst"] or l["split"]["sgst"]):
                    bucket["intra"] += _f(l["taxable"])

    return JsonResponse({
        "weeks": list(buckets.values()),
        "recorded_fields": {
            "order_total": "Order.total_amount",
            "item_sales": "sum(OrderItem.price * OrderItem.quantity), shown without GST when a GST rate is recorded",
            "successful_payment_filter": "Payment.status == PAID",
            "checkout_addons": "Derived from order total minus item subtotal",
            "product_cost": ctx["cost"],
            "sales_gst_rates": ctx["rate"],
            "delivery_state": ctx["state_order"] or ctx["state_customer"],
            "razorpay_gateway_fee": None,
            "refunds_returns": "Paid orders with status " + "/".join(sorted(CANCELLED)),
            "shipping": None,
            "input_tax_credit": None,
            "advertising_spend": None,
            "fixed_expenses": None,
        },
        "notes": [
            "Checkout add-ons are derived values. They are not confirmed gateway fees.",
            "Razorpay fees, shipping, advertising, fixed expenses and input tax credit are not recorded, so they are not estimated.",
            "Products without a recorded GST rate are counted at their recorded price and add nothing to the GST section.",
        ],
    })


# ---- Tax report -------------------------------------------------------------

TAX_TABLES = ("b2b", "b2cl", "b2cs", "cdn", "hsn")


def _month_range(period, span):
    y, m = (int(x) for x in period.split("-"))
    if not 1 <= m <= 12 or span < 1:
        raise ValueError("Invalid period.")
    end_m = m + span
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime(y, m, 1), tz)
    end = timezone.make_aware(datetime(y + (end_m - 1) // 12, (end_m - 1) % 12 + 1, 1), tz)
    return start, end


def _resolve_period(request):
    """Returns (period, span, start, end). Raises ValueError on bad input."""
    period = request.GET.get("period") or timezone.localdate().strftime("%Y-%m")
    span = int(request.GET.get("span", 1))
    start, end = _month_range(period, span)
    return period, span, start, end


def _tax_data(start_dt, end_dt, period, span):
    ctx = _ctx()
    totals = {k: ZERO for k in ("taxable5", "taxable18", "taxableOther", "cgst", "sgst", "igst", "unsplit")}
    invoices = []
    b2cs = defaultdict(lambda: [ZERO, ZERO])
    hsn = defaultdict(lambda: [ZERO, ZERO])
    cdn = []
    no_rate = no_hsn = no_state = bad_gstin = 0
    own_state = BUSINESS_STATE.strip().lower()

    def add(sign, l):
        r = l["rate"]
        key = "taxable5" if r == Decimal("0.05") else "taxable18" if r == Decimal("0.18") else "taxableOther"
        totals[key] += sign * l["taxable"]
        for k, v in l["split"].items():
            totals[k] += sign * v

    for order in _paid_orders(start_dt, end_dt):
        inv = f"ORD-{order.id}"
        day = _local_date(order.created_at).isoformat()
        lines = [_line(order, it, ctx) for it in order.items.all()]
        state = _state(order, ctx)
        gstin = (getattr(order.customer, ctx["gstin"], "") or "").strip() if ctx["gstin"] and order.customer else ""
        rated = [l for l in lines if l["rate"] is not None]

        no_rate += len(lines) - len(rated)
        no_hsn += sum(1 for l in lines if not l["hsn"])
        if not state:
            no_state += 1
        if gstin and len(gstin) != 15:
            bad_gstin += 1
        if not rated:
            continue

        taxable = sum((l["taxable"] for l in rated), ZERO)
        tax = sum((l["tax"] for l in rated), ZERO)
        for l in rated:
            add(1, l)
            h = hsn[(l["hsn"] or "missing", l["rate"])]
            h[0] += l["taxable"]
            h[1] += l["tax"]

        if gstin:
            invoices.append(("b2b", dict(inv=inv, gstin=gstin, date=day, taxable=_f(taxable), tax=_f(tax))))
        elif state and state.lower() != own_state and taxable + tax > B2CL_LIMIT:
            invoices.append(("b2cl", dict(inv=inv, state=state, date=day, value=_f(taxable + tax),
                                          taxable=_f(taxable), tax=_f(tax))))
        else:
            for l in rated:
                b = b2cs[(state or "Unknown", l["rate"])]
                b[0] += l["taxable"]
                b[1] += l["tax"]

        if (order.status or "").upper() in CANCELLED:
            cdn.append(dict(ref=f"CN-{order.id}", date=day, taxable=-_f(taxable), tax=-_f(tax)))
            for l in rated:
                add(-1, l)
                h = hsn[(l["hsn"] or "missing", l["rate"])]
                h[0] -= l["taxable"]
                h[1] -= l["tax"]

    # Posted supplier bills are surfaced as recorded purchase GST. This is NOT
    # automatically eligible input tax credit; eligibility needs invoice-level review.
    purchase_tax = {"cgst": ZERO, "sgst": ZERO, "igst": ZERO, "total": ZERO, "bills": 0}
    if "VendorBill" in globals():
        bill_rows = VendorBill.objects.filter(
            invoice_date__gte=start_dt.date(),
            invoice_date__lt=end_dt.date(),
            status__in=("posted", "partial", "paid"),
        ).aggregate(
            cgst=Sum("cgst_amount"),
            sgst=Sum("sgst_amount"),
            igst=Sum("igst_amount"),
        )
        purchase_tax["cgst"] = bill_rows["cgst"] or ZERO
        purchase_tax["sgst"] = bill_rows["sgst"] or ZERO
        purchase_tax["igst"] = bill_rows["igst"] or ZERO
        purchase_tax["total"] = purchase_tax["cgst"] + purchase_tax["sgst"] + purchase_tax["igst"]
        purchase_tax["bills"] = VendorBill.objects.filter(
            invoice_date__gte=start_dt.date(),
            invoice_date__lt=end_dt.date(),
            status__in=("posted", "partial", "paid"),
        ).count()

    return {
        "period": period, "span": span,
        "totals": {k: _f(v) for k, v in totals.items()},
        "purchase_tax": {k: (_f(v) if isinstance(v, Decimal) else v) for k, v in purchase_tax.items()},
        "b2b": [r for t, r in invoices if t == "b2b"],
        "b2cl": [r for t, r in invoices if t == "b2cl"],
        "b2cs": [dict(state=k[0], rate=float(k[1]), taxable=_f(v[0]), tax=_f(v[1])) for k, v in b2cs.items()],
        "cdn": cdn,
        "hsn": [dict(hsn=k[0], rate=float(k[1]), taxable=_f(v[0]), tax=_f(v[1])) for k, v in hsn.items()],
        "credit": {"goods": 0, "shipping": 0, "fees": 0, "ads": 0, "other": 0},
        "checks": [
            {"label": "Order lines whose product has no GST rate recorded", "count": no_rate},
            {"label": "Order lines with no HSN code recorded", "count": no_hsn},
            {"label": "Paid orders with no delivery state recorded", "count": no_state},
            {"label": "Business buyers with an invalid GSTIN", "count": bad_gstin},
        ],
        "recorded_fields": {
            "paid_orders": "Orders with a Payment whose status is PAID",
            "gst_rate_field": ctx["rate"],
            "hsn_field": ctx["hsn"],
            "delivery_state_field": ctx["state_order"] or ctx["state_customer"],
            "buyer_gstin_field": ctx["gstin"],
            "credit_notes": "Paid orders with status " + "/".join(sorted(CANCELLED)),
            "input_tax_credit": None,
        },
        "notes": [
            "Only products with a recorded GST rate are taxed. Nothing is estimated.",
            "Tax credit from supplier invoices is not recorded yet, so it shows as zero.",
        ],
    }


def admin_tax_gst(request):
    """JSON for the Tax Report: /api/admin/finance/gst/?period=2026-10&span=1"""
    denied = _admin_or_401(request)
    if denied:
        return denied
    try:
        period, span, start, end = _resolve_period(request)
    except ValueError:
        return JsonResponse({"detail": "Invalid period or span."}, status=400)
    return JsonResponse(_tax_data(start, end, period, span))


def admin_tax_csv(request, table):
    """One GSTR-1 table as CSV for your accountant: b2b, b2cl, b2cs, cdn or hsn."""
    denied = _admin_or_401(request)
    if denied:
        return denied
    if table not in TAX_TABLES:
        return HttpResponse("Unknown table", status=404)
    try:
        period, span, start, end = _resolve_period(request)
    except ValueError:
        return HttpResponse("Invalid period or span.", status=400)

    rows = _tax_data(start, end, period, span)[table]
    res = HttpResponse(content_type="text/csv")
    res["Content-Disposition"] = f'attachment; filename="gst-{table}-{period}.csv"'
    out = csv.writer(res)
    cols = list(rows[0].keys()) if rows else ["no entries"]
    out.writerow(cols)
    for r in rows:
        out.writerow([r[c] for c in cols])
    return res


def admin_ledger_csv(request, fy):
    """Every invoice line and credit note for a financial year, e.g. /finance/ledger/2026-27.csv"""
    denied = _admin_or_401(request)
    if denied:
        return denied
    try:
        y = int(fy[:4])
    except ValueError:
        return HttpResponse("Invalid financial year.", status=400)

    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime(y, 4, 1), tz)
    end = timezone.make_aware(datetime(y + 1, 4, 1), tz)
    ctx = _ctx()

    res = HttpResponse(content_type="text/csv")
    res["Content-Disposition"] = f'attachment; filename="uncommon-tax-ledger-{fy}.csv"'
    out = csv.writer(res)
    out.writerow(["date", "type", "reference", "state", "hsn", "gst_rate", "taxable",
                  "cgst", "sgst", "igst", "unsplit_tax", "note"])

    for order in _paid_orders(start, end):
        day = _local_date(order.created_at).isoformat()
        state = _state(order, ctx)
        cancelled = (order.status or "").upper() in CANCELLED
        entries = [("SALE", 1), ("CREDIT_NOTE", -1)] if cancelled else [("SALE", 1)]

        for it in order.items.all():
            l = _line(order, it, ctx)
            sp = l["split"] or {}
            for kind, sign in entries:
                out.writerow([
                    day, kind, f"ORD-{order.id}", state, l["hsn"],
                    "" if l["rate"] is None else float(l["rate"]),
                    _f(sign * l["taxable"]),
                    _f(sign * sp.get("cgst", ZERO)),
                    _f(sign * sp.get("sgst", ZERO)),
                    _f(sign * sp.get("igst", ZERO)),
                    _f(sign * sp.get("unsplit", ZERO)),
                    "" if l["rate"] is not None else "No GST rate recorded for this product",
                ])
    return res


# =============================================================================
# 5. CATEGORIES
# =============================================================================

SECTIONS = ["HIM", "HER", "RARE"]


@admin_required
def view_categories(request):
    categories = Category.objects.all().order_by("-id")

    search = request.GET.get("search", "").strip()
    if search:
        categories = categories.filter(category_name__icontains=search)

    section = request.GET.get("section", "").strip()
    if section in SECTIONS:
        categories = categories.filter(section=section)

    return render(request, "admin_panel/categories.html", {
        "admin": request.admin_user,
        "page_obj": _paginate(request, categories, 10),
        "search": search,
        "section": section,
    })


@require_POST
@admin_required
def add_category(request):
    section = request.POST.get("section")
    category_name = request.POST.get("category_name")
    description = request.POST.get("description")

    if not section or not category_name:
        messages.error(request, "Section and category name are required.")
        return redirect("view_categories")

    Category.objects.create(section=section, category_name=category_name, description=description)
    messages.success(request, f'"{category_name}" category added successfully.')
    return redirect("view_categories")


@require_POST
@admin_required
def edit_category(request, id):
    category = get_object_or_404(Category, id=id)

    section = request.POST.get("section")
    category_name = request.POST.get("category_name")
    description = request.POST.get("description")

    if not section or not category_name:
        messages.error(request, "Section and category name are required.")
        return redirect("view_categories")

    category.section = section
    category.category_name = category_name
    category.description = description
    category.save()

    messages.success(request, f'"{category_name}" category updated successfully.')
    return redirect("view_categories")


@require_POST
@admin_required
def delete_category(request, id):
    category = get_object_or_404(Category, id=id)
    category_name = category.category_name

    try:
        category.delete()
        messages.success(request, f'"{category_name}" deleted successfully.')
    except ProtectedError:
        messages.error(request, f'Cannot delete "{category_name}" because products are using this category.')

    return redirect("view_categories")


# =============================================================================
# 6. PRODUCTS
# =============================================================================

IMAGE_FIELDS = ("image", "image2", "image3", "image4")



def _clean_product_form(request):
    """Validate product data, financial fields and shipping dimensions."""

    post = request.POST

    category_id = post.get("category", "").strip()
    product_name = post.get("product_name", "").strip()
    overview = post.get("overview", "").strip()
    description = post.get("description", "").strip()

    price_input = post.get("price", "").strip()
    stock_input = post.get("stock", "").strip()

    cost_input = post.get("cost_price", "").strip()
    gst_input = post.get("gst_rate", "").strip()
    hsn_code = post.get("hsn_code", "").strip()

    weight_input = post.get("weight", "").strip()
    length_input = post.get("length", "").strip()
    breadth_input = post.get("breadth", "").strip()
    height_input = post.get("height", "").strip()

    if not category_id or not product_name:
        raise ValueError("Category and product name are required.")

    if len(product_name) > 150:
        raise ValueError("Product name must be 150 characters or fewer.")

    if len(overview) > 1000:
        raise ValueError("Overview must be 1000 characters or fewer.")

    if len(hsn_code) > 20:
        raise ValueError("HSN code must be 20 characters or fewer.")

    if not price_input or not stock_input:
        raise ValueError("Product price and stock are required.")

    try:
        category = Category.objects.get(id=category_id)
    except (Category.DoesNotExist, ValueError, TypeError):
        raise ValueError("Selected category does not exist.")

    try:
        price = Decimal(price_input)
        stock = int(stock_input)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Please enter valid price and stock values.")

    if (
        not price.is_finite()
        or price < 0
        or price > Decimal("99999999.99")
        or price.as_tuple().exponent < -2
        or stock < 0
    ):
        raise ValueError("Please enter valid price and stock values.")

    # Cost price
    cost_price = None

    if cost_input:
        try:
            cost_price = Decimal(cost_input)
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError("Please enter a valid cost price.")

        if (
            not cost_price.is_finite()
            or cost_price < 0
            or cost_price > Decimal("99999999.99")
            or cost_price.as_tuple().exponent < -2
        ):
            raise ValueError(
                "Cost price must be non-negative and have at most 2 decimal places."
            )

    # GST rate
    gst_rate = None

    if gst_input:
        try:
            gst_rate = Decimal(gst_input)
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError("Please enter a valid GST rate.")

        if (
            not gst_rate.is_finite()
            or gst_rate < 0
            or gst_rate > 100
            or gst_rate.as_tuple().exponent < -2
        ):
            raise ValueError(
                "GST rate must be between 0 and 100 with at most 2 decimal places."
            )

    # Shiprocket shipping dimensions
    try:
        weight = Decimal(weight_input)
        length = Decimal(length_input)
        breadth = Decimal(breadth_input)
        height = Decimal(height_input)

    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Please enter valid shipping dimensions.")

    if (
        not weight.is_finite()
        or weight <= 0
        or weight > Decimal("99999.999")
        or weight.as_tuple().exponent < -3
    ):
        raise ValueError(
            "Weight must be greater than zero and have at most 3 decimal places."
        )

    dimensions = {
        "Length": length,
        "Breadth": breadth,
        "Height": height,
    }

    for field, value in dimensions.items():

        if (
            not value.is_finite()
            or value <= Decimal("0.50")
            or value > Decimal("999999.99")
            or value.as_tuple().exponent < -2
        ):
            raise ValueError(
                f"{field} must be greater than 0.5 CM "
                "and have at most 2 decimal places."
            )

    return {
        "category": category,
        "product_name": product_name,
        "overview": overview,
        "description": description,
        "price": price,
        "cost_price": cost_price,
        "gst_rate": gst_rate,
        "hsn_code": hsn_code,
        "stock": stock,

        # Shipping details
        "weight": weight,
        "length": length,
        "breadth": breadth,
        "height": height,

        "is_rare": post.get("is_rare") == "on",
        "is_limited": post.get("is_limited") == "on",
    }


@admin_required
def view_products(request):
    from django.db.models import Q

    categories = Category.objects.all().order_by(
        "section", "category_name"
    )

    channel = request.GET.get("channel", "B2C").upper()

    if channel not in ["B2B", "B2C"]:
        channel = "B2C"

    # Exclude archived products from active product list
    products = (
        Product.objects
        .filter(is_archived=False)
        .select_related("category")
        .order_by("-id")
    )

    # B2B / B2C separation
    if channel == "B2B":
        products = products.filter(
            category__category_name__iexact="Purchase Entries"
        )
    else:
        products = products.exclude(
            category__category_name__iexact="Purchase Entries"
        )

    # Search
    search = request.GET.get("search", "").strip()

    if search:
        products = products.filter(
            Q(product_name__icontains=search)
            | Q(overview__icontains=search)
            | Q(description__icontains=search)
        )

    # Section filter
    section = request.GET.get("section", "").strip()

    if section in SECTIONS:
        products = products.filter(
            category__section=section
        )

    # Category filter
    category_id = request.GET.get("category", "").strip()

    if category_id:
        products = products.filter(
            category_id=category_id
        )

    # Categories available for inventory filtering
    filter_categories = categories.exclude(
        category_name__iexact="Purchase Entries"
    )

    return render(
        request,
        "admin_panel/products.html",
        {
            "admin": request.admin_user,
            "page_obj": _paginate(request, products, 5),
            "categories": categories,
            "filter_categories": filter_categories,
            "search": search,
            "section": section,
            "category_id": category_id,
            "channel": channel,

            "low_stock_count": products.filter(
                stock__gt=0,
                stock__lte=5
            ).count(),

            "out_of_stock_count": products.filter(
                stock=0
            ).count(),
        }
    )
@require_POST
@admin_required
def move_product_to_inventory(request, id):

    product = get_object_or_404(
        Product,
        id=id,
        category__category_name__iexact="Purchase Entries"
    )

    category_id = request.POST.get("category")

    if not category_id:
        messages.error(request, "Please select an inventory category.")
        return redirect(f"{reverse('view_products')}?channel=B2B")

    category = get_object_or_404(
        Category.objects.exclude(
            category_name__iexact="Purchase Entries"
        ),
        id=category_id
    )

    product.category = category
    product.save(update_fields=["category"])

    messages.success(
        request,
        f'"{product.product_name}" moved to your inventory successfully.'
    )

    return redirect(f"{reverse('view_products')}?channel=B2C")

def _notify_subscribers(request, product):
    """Email upcoming-release subscribers whose interest matches the new product."""
    if product.stock <= 0:
        messages.info(request, "The product has no stock yet, so subscriber emails were not sent.")
        return

    interests = ["New product launch", "Any upcoming release"]
    if product.is_rare:
        interests.append("The Hundred — next rare release")
    if product.is_limited:
        interests.append("Limited-edition product")

    # One email per address (the earliest matching subscription).
    first_by_email = {}
    for sub in UpcomingReservation.objects.filter(interest__in=interests).order_by("id"):
        first_by_email.setdefault(sub.email, sub)

    subject = f"INSOLO UNCOMMON | New Release: {product.product_name}"
    sent = failed = 0

    for email, sub in first_by_email.items():
        body = f"""
Hello {sub.name or 'Customer'},

Good news! A new product matching your interests is now available.

Product: {product.product_name}
Price: ₹{product.price}

Your interest: {sub.interest or 'Upcoming release'}

Visit INSOLO UNCOMMON to explore our latest collection.

Thank you for your interest.

INSOLO UNCOMMON — The House
        """.strip()
        try:
            send_mail(
                subject=subject,
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )
            sent += 1
        except Exception:
            logger.exception("New-product email failed for %s", email)
            failed += 1

    if sent:
        messages.success(request, f"Availability notification sent to {sent} subscriber(s).")
    if failed:
        messages.warning(request, f"{failed} notification email(s) could not be sent.")
    if not sent and not failed:
        messages.info(request, "No subscribers matched this product.")


@require_POST
@admin_required
def add_product(request):
    try:
        data = _clean_product_form(request)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("view_products")

    # The primary image is required; the other three are optional.
    images = {field: request.FILES.get(field) for field in IMAGE_FIELDS}
    if not images["image"]:
        messages.error(request, "The main product image is required.")
        return redirect("view_products")

    product = Product.objects.create(**data, **images)
    messages.success(request, f'"{product.product_name}" added successfully.')

    _notify_subscribers(request, product)
    return redirect("view_products")


@require_POST
@admin_required
def edit_product(request, id):
    product = get_object_or_404(Product, id=id)

    is_b2b = (
        product.category.category_name.strip().lower()
        == "purchase entries"
    )

    try:
        data = _clean_product_form(request)

        # B2B products must remain in Purchase Entries
        # until the separate Move action is used.
        if is_b2b:
            data.pop("category", None)

        else:
            selected_category = data.get("category")

            if (
                selected_category
                and selected_category.category_name.strip().lower()
                == "purchase entries"
            ):
                raise ValueError(
                    "Use the B2B Purchase Entries section "
                    "to manage purchase products."
                )

    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect(
            f"{reverse('view_products')}?channel={'B2B' if is_b2b else 'B2C'}"
        )

    for field, value in data.items():
        setattr(product, field, value)

    # Preserve existing images unless replacement files are uploaded.
    for field in IMAGE_FIELDS:
        uploaded = request.FILES.get(field)

        if uploaded:
            setattr(product, field, uploaded)

    product.save()

    messages.success(
        request,
        f'"{product.product_name}" updated successfully.'
    )

    return redirect(
        f"{reverse('view_products')}?channel={'B2B' if is_b2b else 'B2C'}"
    )

@require_POST
@admin_required
def delete_product(request, id):
    product = get_object_or_404(Product, id=id)

    name = product.product_name

    product.is_archived = True
    product.save(update_fields=["is_archived"])

    messages.success(
        request,
        f'"{name}" archived successfully.'
    )

    return redirect("view_products")
# =============================================================================
# 7. CUSTOMERS
# =============================================================================

@admin_required
def view_customers(request):
    customers = Customer.objects.all().order_by("-id")

    search = request.GET.get("search", "").strip()
    if search:
        customers = customers.filter(
            Q(name__icontains=search)
            | Q(email__icontains=search)
            | Q(username__icontains=search)
            | Q(phone__icontains=search)
        )

    return render(request, "admin_panel/customers.html", {
        "admin": request.admin_user,
        "page_obj": _paginate(request, customers, 10),
        "search": search,
        "total_customers": Customer.objects.count(),
    })


@require_POST
@admin_required
def edit_customer(request, id):
    customer = get_object_or_404(Customer, id=id)

    name = request.POST.get("name", "").strip()
    email = request.POST.get("email", "").strip()
    phone = request.POST.get("phone", "").strip()
    username = request.POST.get("username", "").strip()

    if not name or not email or not username:
        messages.error(request, "Name, email and username are required.")
        return redirect("view_customers")

    if Customer.objects.filter(email=email).exclude(id=id).exists():
        messages.error(request, "This email is already registered.")
        return redirect("view_customers")

    if Customer.objects.filter(username=username).exclude(id=id).exists():
        messages.error(request, "This username is already taken.")
        return redirect("view_customers")

    customer.name = name
    customer.email = email
    customer.phone = phone
    customer.username = username
    customer.save()

    messages.success(request, f'"{customer.name}" updated successfully.')
    return redirect("view_customers")


@require_POST
@admin_required
def delete_customer(request, id):
    customer = get_object_or_404(Customer, id=id)
    name = customer.name
    customer.delete()
    messages.success(request, f'"{name}" deleted successfully.')
    return redirect("view_customers")


# =============================================================================
# 8. ORDERS
# =============================================================================

@admin_required
def view_orders(request):
    orders = (
        Order.objects
        .select_related("customer")
        .prefetch_related("items__product")
        .order_by("-created_at")
    )

    search = request.GET.get("search", "").strip()
    if search:
        orders = orders.filter(
            Q(order_number__icontains=search)
            | Q(customer__name__icontains=search)
            | Q(customer__email__icontains=search)
        )

    status = request.GET.get("status", "").strip()
    if status in ORDER_STATUSES:
        orders = orders.filter(status=status)

    # One query for all the status counters.
    counts = {row["status"]: row["n"] for row in Order.objects.values("status").annotate(n=Count("id"))}

    page_obj = _paginate(request, orders, 10)

    order_items_data = {
        str(order.id): [
            {
                "product": item.product.product_name,
                "quantity": item.quantity,
                "price": float(item.price),
                "total": float(item.price * item.quantity),
            }
            for item in order.items.all()
        ]
        for order in page_obj
    }

    return render(request, "admin_panel/orders.html", {
        "admin": request.admin_user,
        "page_obj": page_obj,
        "search": search,
        "status": status,
        "total_orders": sum(counts.values()),
        "pending_orders": counts.get("PENDING", 0),
        "confirmed_orders": counts.get("CONFIRMED", 0),
        "shipped_orders": counts.get("SHIPPED", 0),
        "delivered_orders": counts.get("DELIVERED", 0),
        "cancelled_orders": counts.get("CANCELLED", 0),
        "order_items_json": json.dumps(order_items_data),
    })


# def _send_brevo_email(to_email, subject, text):
#     """Send a plain-text email through the Brevo HTTPS API. Raises on any failure."""
#     api_key = settings.BREVO_API_KEY
#     sender_email = settings.BREVO_SENDER_EMAIL
#     if not api_key or not sender_email:
#         raise ValueError("Brevo API key or sender email is not configured.")

#     response = requests.post(
#         "https://api.brevo.com/v3/smtp/email",
#         headers={
#             "accept": "application/json",
#             "api-key": api_key,
#             "content-type": "application/json",
#         },
#         json={
#             "sender": {"name": "UNCOMMON Team", "email": sender_email},
#             "to": [{"email": to_email}],
#             "subject": subject,
#             "textContent": text,
#         },
#         timeout=15,
#     )
#     response.raise_for_status()


import logging

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST
from customer.shiprocket_service import (
    create_shiprocket_order,
    cancel_shiprocket_order,
)
from customer.models import ShiprocketShipment
logger = logging.getLogger(__name__)

from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction


def refund_paid_prepaid_order(order):
    payment = (
        Payment.objects
        .filter(
            order=order,
            status="PAID",
            razorpay_payment_id__isnull=False,
        )
        .exclude(razorpay_payment_id="")
        .order_by("-id")
        .first()
    )

    if not payment:
        return False, "No successful Razorpay payment was found."

    if payment.refund_status == "PROCESSED":
        return True, "Refund has already been processed."

    if payment.refund_status == "PENDING":
        return False, (
            "A refund is already pending. Check Razorpay before retrying."
        )

    amount_paise = int(
        (Decimal(str(payment.amount)) * Decimal("100"))
        .quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )

    if amount_paise <= 0:
        return False, "The payment amount is invalid for a refund."

    # Mark pending before calling Razorpay to reduce duplicate requests.
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment.pk)

        if payment.refund_status in {"PENDING", "PROCESSED"}:
            return False, (
                "A refund is already pending or processed. "
                "Check Razorpay before retrying."
            )

        payment.refund_status = "PENDING"
        payment.save(update_fields=["refund_status"])

    try:
        client = get_razorpay_client()
        refund = client.payment.refund(
            payment.razorpay_payment_id,
            {
                "amount": amount_paise,
                "notes": {
                    "order_number": str(order.order_number),
                    "reason": "Admin cancelled order",
                },
            },
        )
    except Exception:
        # Keep PENDING: the request may have reached Razorpay even if
        # our server did not receive its response. Check Razorpay first.
        logger.exception(
            "Razorpay refund result uncertain for order %s",
            order.order_number,
        )
        return False, (
            "Razorpay returned no clear result. Check its dashboard "
            "before retrying."
        )

    payment.refresh_from_db()
    payment.razorpay_refund_id = refund.get("id")

    refund_api_status = (refund.get("status") or "").lower()

    if refund_api_status == "processed":
        payment.refund_status = "PROCESSED"
        message = "Razorpay refund processed."
    elif refund_api_status == "failed":
        payment.refund_status = "FAILED"
        message = "Razorpay refund failed. The order was not cancelled."
    else:
        payment.refund_status = "PENDING"
        message = "Razorpay accepted the refund request; it is pending."

    payment.save(update_fields=["razorpay_refund_id", "refund_status"])

    return refund_api_status != "failed", message

@require_POST
@admin_required
def update_order_status(request, id):
    """
    UNCOMMEN Admin Order Status Workflow

    COD:
      - Stock deducted when admin confirms.
      - Payment remains COD_PENDING.
      - Stock restored when a confirmed COD order is cancelled.

    PREPAID:
      - Can only be confirmed after payment is PAID.
      - Stock is deducted by finalize_captured_payment().
      - Paid prepaid orders are refunded before cancellation.

    SHIPROCKET:
      - Shiprocket order created after confirmation.
      - Existing Shiprocket shipment cancelled when admin cancels.
      - Shipped and Delivered are controlled by tracking.
    """

    new_status = request.POST.get("status", "").strip()

    if new_status not in ORDER_STATUSES:
        messages.error(request, "Invalid order status.")
        return redirect("view_orders")

    should_create_shipment = False
    should_cancel_shipment = False

    try:
        # ==========================================
        # STEP 1: FETCH ORDER
        # ==========================================

        order = (
            Order.objects
            .select_related("customer")
            .get(id=id)
        )

        if new_status == order.status:
            messages.info(
                request,
                "The order already has this status."
            )
            return redirect("view_orders")

        # Shipping milestones must come from Shiprocket.
        if new_status in {"SHIPPED", "DELIVERED"}:
            messages.error(
                request,
                "Shipped and Delivered statuses are updated through Shiprocket tracking."
            )
            return redirect("view_orders")

        # Prevent normal cancellation after shipping.
        if (
            new_status == "CANCELLED"
            and order.status in {"SHIPPED", "DELIVERED"}
        ):
            messages.error(
                request,
                "This order has already been shipped or delivered. "
                "Use the return/cancellation process instead."
            )
            return redirect("view_orders")

        # ==========================================
        # STEP 2: PREPARE SHIPROCKET CANCELLATION
        # ==========================================

        if new_status == "CANCELLED":
            should_cancel_shipment = True

        # ==========================================
        # STEP 3: SHIPROCKET CANCELLATION
        # ==========================================

        # Call the external API outside transaction.atomic().
        # This avoids holding database locks during network requests.

        if should_cancel_shipment:
            order.refresh_from_db()

            # Check whether a Shiprocket shipment exists.
            try:
                shipment = order.shipment
            except ShiprocketShipment.DoesNotExist:
                shipment = None

            if shipment and shipment.shiprocket_order_id:
                cancellation_success = cancel_shiprocket_order(order)

                if not cancellation_success:
                    messages.error(
                        request,
                        "Shiprocket cancellation failed. "
                        "The UNCOMMEN order was not cancelled. "
                        "Please check the Shiprocket dashboard and shipment error."
                    )
                    return redirect("view_orders")

        # ==========================================
        # STEP 3B: RAZORPAY REFUND
        # ==========================================

        if (
            new_status == "CANCELLED"
            and order.payment_method == "PREPAID"
            and order.payment_status == "PAID"
        ):
            refund_success, refund_message = (
                refund_paid_prepaid_order(order)
            )

            if not refund_success:
                messages.error(
                    request,
                    f"Order was not cancelled. {refund_message}"
                )
                return redirect("view_orders")

            messages.info(request, refund_message)

        # ==========================================
        # STEP 4: UPDATE ORDER IN DATABASE
        # ==========================================

        with transaction.atomic():
            order = (
                Order.objects
                .select_for_update()
                .select_related("customer")
                .get(id=id)
            )

            # Recheck status in case another admin changed it.
            if order.status == new_status:
                messages.info(
                    request,
                    "The order status was already updated."
                )
                return redirect("view_orders")

            if order.status in {"SHIPPED", "DELIVERED"}:
                messages.error(
                    request,
                    "This order has already been shipped or delivered."
                )
                return redirect("view_orders")

            # ======================================
            # CONFIRM ORDER
            # ======================================

            if new_status == "CONFIRMED":

                if order.payment_method == "PREPAID":
                    if order.payment_status != "PAID":
                        messages.error(
                            request,
                            "Prepaid order cannot be confirmed until Razorpay payment is verified."
                        )
                        return redirect("view_orders")

                elif order.payment_method == "COD":
                    if order.payment_status not in {
                        "COD_PENDING",
                        "PENDING",
                    }:
                        messages.error(
                            request,
                            "This COD order is not in a confirmable payment state."
                        )
                        return redirect("view_orders")

                    # Get order items.
                    items = list(
                        order.items
                        .select_related("product")
                        .order_by("product_id")
                    )

                    if not items:
                        messages.error(
                            request,
                            "Cannot confirm an order without products."
                        )
                        return redirect("view_orders")

                    product_ids = [
                        item.product_id
                        for item in items
                    ]

                    # Lock products in stable order.
                    locked_products = {
                        product.id: product
                        for product in (
                            Product.objects
                            .select_for_update()
                            .filter(id__in=product_ids)
                            .order_by("id")
                        )
                    }

                    # Aggregate quantities.
                    required_quantities = {}

                    for item in items:
                        required_quantities[item.product_id] = (
                            required_quantities.get(
                                item.product_id, 0
                            ) + item.quantity
                        )

                    # Validate stock.
                    insufficient = []

                    for product_id, required_qty in (
                        required_quantities.items()
                    ):
                        product = locked_products.get(product_id)

                        if product is None:
                            insufficient.append(
                                f"Product #{product_id} unavailable"
                            )
                            continue

                        if product.stock < required_qty:
                            insufficient.append(
                                f"{product.product_name}: "
                                f"only {product.stock} available, "
                                f"{required_qty} ordered"
                            )

                    if insufficient:
                        messages.error(
                            request,
                            "Cannot confirm COD order. Insufficient stock: "
                            + "; ".join(insufficient)
                        )
                        return redirect("view_orders")

                    # Deduct stock once.
                    for product_id, required_qty in (
                        required_quantities.items()
                    ):
                        product = locked_products[product_id]
                        product.stock -= required_qty
                        product.save(update_fields=["stock"])

                    order.payment_status = "COD_PENDING"

                should_create_shipment = True

            # ======================================
            # CANCEL ORDER
            # ======================================

            if new_status == "CANCELLED":

                # Restore stock for any confirmed order.
                # Stock was already deducted for both COD and prepaid.
                if order.status == "CONFIRMED":
                    items = list(
                        order.items
                        .select_related("product")
                        .order_by("product_id")
                    )

                    # Aggregate quantities if a product appears
                    # in multiple order items.
                    restore_quantities = {}

                    for item in items:
                        restore_quantities[item.product_id] = (
                            restore_quantities.get(item.product_id, 0)
                            + item.quantity
                        )

                    # Lock products in a stable order.
                    locked_products = {
                        product.id: product
                        for product in (
                            Product.objects
                            .select_for_update()
                            .filter(id__in=restore_quantities.keys())
                            .order_by("id")
                        )
                    }

                    # Restore stock.
                    for product_id, quantity in restore_quantities.items():
                        product = locked_products.get(product_id)

                        if product:
                            product.stock += quantity
                            product.save(update_fields=["stock"])

            # ======================================
            # SAVE ORDER
            # ======================================

            order.status = new_status

            update_fields = [
                "status",
                "updated_at",
            ]

            if (
                new_status == "CONFIRMED"
                and order.payment_method == "COD"
            ):
                update_fields.append("payment_status")

            order.save(update_fields=update_fields)

    except Order.DoesNotExist:
        messages.error(
            request,
            "Order not found."
        )
        return redirect("view_orders")

    except Exception:
        logger.exception(
            "Failed to update order status for order id %s",
            id
        )
        messages.error(
            request,
            "Unable to update order status. Check server logs."
        )
        return redirect("view_orders")

    # ==========================================
    # STEP 5: CREATE SHIPROCKET ORDER
    # ==========================================

    if should_create_shipment:
        try:
            order.refresh_from_db()

            success = create_shiprocket_order(order)

            if success:
                messages.success(
                    request,
                    "Order confirmed and Shiprocket order created successfully."
                )
            else:
                messages.warning(
                    request,
                    "Order confirmed, but Shiprocket order creation failed. "
                    "Check shipment error details."
                )

        except Exception:
            logger.exception(
                "Shiprocket creation failed for order %s",
                order.order_number
            )
            messages.warning(
                request,
                "Order confirmed, but Shiprocket integration failed."
            )

    # ==========================================
    # STEP 6: CUSTOMER EMAIL
    # ==========================================

    customer_email = order.customer.email

    if not customer_email:
        messages.warning(
            request,
            "Order status updated, but customer has no email address."
        )
        return redirect("view_orders")

    subject_text, message_text = ORDER_STATUS_EMAILS[new_status]

    payment_note = (
        "\nPayment Method: Cash on Delivery"
        "\nPayment Status: Pay on delivery"
        if order.payment_method == "COD"
        else "\nPayment Method: Prepaid"
        "\nPayment Status: Paid"
    )

    body = f"""
Hello {getattr(order.customer, 'name', '') or 'Customer'},

{message_text}

Order Number: {order.order_number}
Order Total: ₹{order.total_amount}
Current Status: {order.get_status_display()}
{payment_note}

Thank you for choosing UNCOMMEN.

Regards,
UNCOMMEN Team
    """.strip()

    try:
        _send_brevo_email(
            customer_email,
            f"UNCOMMEN | {subject_text}",
            body
        )

        messages.success(
            request,
            f"Order status updated. Email submitted to Brevo for {customer_email}."
        )

    except Exception:
        logger.exception(
            "Failed to send order status email through Brevo"
        )
        messages.warning(
            request,
            "Order status updated, but the email could not be sent."
        )

    return redirect("view_orders")

@admin_required
def test_email(request):
    try:
        sent = send_mail(
            subject="Render Email Test",
            message="Testing email from Django on Render.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.EMAIL_HOST_USER],
            fail_silently=False,
        )
        return JsonResponse({"sent": sent})
    except Exception as exc:
        logger.exception("Email test failed")
        return JsonResponse({"error": type(exc).__name__, "message": str(exc)}, status=500)


# =============================================================================
# 9. FEEDBACK
# =============================================================================

@admin_required
def admin_feedback(request):
    
    if not request.session.get("admin"):
        return redirect("admin_login")

    feedbacks = Feedback.objects.select_related(
        "customer",
        "product"
    ).order_by("-created_at")

    stats = Feedback.objects.aggregate(
        total=Count("id"),
        average=Avg("rating"),
    )

    five_star_count = Feedback.objects.filter(
        rating=5
    ).count()

    return render(
        request,
        "admin_panel/feedback_list.html",
        {
            "feedbacks": feedbacks,
            "total_feedback": stats["total"] or 0,
            "average_rating": round(stats["average"] or 0, 1),
            "five_star_count": five_star_count,
        }
    )


@require_POST
def add_feedback(request, order_number, product_id):
    customer = get_logged_in_customer(request)
    if not customer:
        messages.error(request, "Please log in to submit feedback.")
        return redirect("login")

    # The order must belong to this customer and be delivered.
    order = get_object_or_404(Order, order_number=order_number, customer=customer, status="DELIVERED")
    product = get_object_or_404(Product, pk=product_id)

    if not order.items.filter(product=product).exists():
        messages.error(request, "This product does not belong to this order.")
        return redirect("my_orders")

    comment = request.POST.get("comment", "").strip()
    try:
        rating = int(request.POST.get("rating", ""))
    except (TypeError, ValueError):
        rating = 0

    if rating not in range(1, 6):
        messages.error(request, "Please select a rating from 1 to 5.")
        return redirect("my_orders")
    if not comment:
        messages.error(request, "Please enter a feedback comment.")
        return redirect("my_orders")
    if len(comment) > 1000:
        messages.error(request, "Feedback must be 1000 characters or fewer.")
        return redirect("my_orders")

    _, created = Feedback.objects.get_or_create(
        customer=customer,
        product=product,
        order_number=order.order_number,
        defaults={"rating": rating, "comment": comment},
    )

    if created:
        messages.success(request, "Thank you! Your feedback has been submitted.")
    else:
        messages.info(request, "You have already submitted feedback for this product and order.")
    return redirect("my_orders")


@require_POST
def delete_feedback(request, feedback_id):
    customer = get_logged_in_customer(request)
    if not customer:
        messages.error(request, "Please log in first.")
        return redirect("login")

    get_object_or_404(Feedback, pk=feedback_id, customer=customer).delete()
    messages.success(request, "Your feedback has been deleted.")
    return redirect("my_orders")


# =============================================================================
# 10. PURCHASING
# =============================================================================

def money(value):
    return Decimal(str(value or "0")).quantize(CENT, rounding=ROUND_HALF_UP)


def dec(value, label, default="0"):
    """Parse a Decimal from form input, raising ValueError with a friendly message."""
    try:
        result = Decimal(str(value if value not in (None, "") else default))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"Enter a valid {label}.")
    if not result.is_finite():
        raise ValueError(f"Enter a valid {label}.")
    return result


def _temp_number(prefix):
    """Unique placeholder number, replaced by _finish_number once the row has an id."""
    return f"{prefix}-{timezone.localdate():%Y%m%d}-{secrets.token_hex(5).upper()}"


def _finish_number(obj, prefix, field):
    """Final, human-friendly number such as UNPO-20261108-00042."""
    setattr(obj, field, f"{prefix}-{timezone.localdate():%Y%m%d}-{obj.pk:05d}")
    obj.save(update_fields=[field])


def _active_supplier(request):
    try:
        supplier = Supplier.objects.filter(pk=request.POST.get("supplier"), is_active=True).first()
    except (TypeError, ValueError):
        supplier = None
    if supplier is None:
        raise ValueError("Please select a valid supplier.")
    return supplier


def _product_category():
    category, _ = Category.objects.get_or_create(
        section="RARE",
        category_name="Purchase Entries",
        defaults={"description": "Products created through purchasing"},
    )
    return category


def _snapshot_supplier(supplier, order):
    """Copy the supplier's addresses onto the PO so later supplier edits don't change old orders."""
    order.billing_address = supplier.billing_address or ""
    order.shipping_address = supplier.shipping_address or supplier.billing_address or ""
    order.shipping_city = supplier.shipping_city or supplier.billing_city or ""
    order.shipping_state = supplier.shipping_state or supplier.billing_state or ""
    order.shipping_postal_code = supplier.shipping_postal_code or supplier.billing_postal_code or ""


def _refresh_po_payment_status(order):
    """Recalculate a purchase order's payment status from its vendor bills."""
    bills = VendorBill.objects.filter(purchase_order_id=order.pk).exclude(status=VendorBill.Status.CANCELLED)

    if bills.exists() and not bills.exclude(status=VendorBill.Status.PAID).exists():
        status = PurchaseOrder.PaymentStatus.PAID
    elif bills.filter(amount_paid__gt=0).exists():
        status = PurchaseOrder.PaymentStatus.PARTIAL
    else:
        status = PurchaseOrder.PaymentStatus.UNPAID

    order.payment_status = status
    order.save(update_fields=["payment_status", "updated_at"])


def purchasing_dashboard_context():
    """
    Extra context for the purchasing modals (suppliers, receipts, bills, payments, JSON payloads).
    Merge it into a view's context with: context.update(purchasing_dashboard_context())
    """
    open_po_lines = (
        PurchaseOrderLine.objects
        .select_related("product", "purchase_order")
        .filter(purchase_order__status__in=["draft", "submitted", "approved", "sent", "partial"])
        .order_by("purchase_order_id", "id")
    )

    return {
        "suppliers": Supplier.objects.order_by("company_name"),
        "purchase_orders": (
            PurchaseOrder.objects.select_related("supplier")
            .prefetch_related("lines__product")
            .order_by("-created_at")[:100]
        ),
        "goods_receipts": (
            GoodsReceipt.objects.select_related("supplier", "purchase_order").order_by("-created_at")[:50]
        ),
        "vendor_bills": (
            VendorBill.objects.select_related("supplier", "purchase_order").order_by("-created_at")[:50]
        ),
        "vendor_payments": VendorPayment.objects.select_related("supplier").order_by("-created_at")[:50],
        "procurement_products": [
            {"id": p.pk, "name": p.product_name} for p in Product.objects.order_by("product_name")
        ],
        "procurement_categories": [
            {"id": c.pk, "name": c.category_name, "section": c.section}
            for c in Category.objects.order_by("category_name")
        ],
        "procurement_po_lines": [
            {
                "id": line.pk,
                "po_id": line.purchase_order_id,
                "product": line.product.product_name,
                "ordered": str(line.quantity),
                "received": str(line.received_quantity),
                "remaining": str(line.quantity - line.received_quantity),
            }
            for line in open_po_lines
        ],
        "procurement_bills": [
            {
                "id": b.pk,
                "supplier_id": b.supplier_id,
                "number": b.bill_number,
                "invoice": b.supplier_invoice_number,
                "due": str(b.amount_due),
            }
            for b in VendorBill.objects.exclude(status="cancelled").order_by("-id")[:200]
        ],
    }


# ---- Purchase order list ----------------------------------------------------

@admin_required
@finance_required
def purchases(request):
    purchase_orders = PurchaseOrder.objects.select_related("supplier").order_by("-created_at")
    Status = PurchaseOrder.Status

    return render(request, "admin_panel/purchases.html", {
        "admin": request.admin_user,
        "purchase_orders": purchase_orders,
        "purchase_status_choices": Status.choices,
        "total_orders": purchase_orders.count(),
        "pending_orders": purchase_orders.filter(
            status__in=[Status.SUBMITTED, Status.APPROVED, Status.SENT, Status.PARTIAL]
        ).count(),
        "received_orders": purchase_orders.filter(status=Status.RECEIVED).count(),
        "cancelled_orders": purchase_orders.filter(status=Status.CANCELLED).count(),
        "total_amount": purchase_orders.aggregate(total=Sum("grand_total"))["total"] or ZERO,
    })


# ---- Suppliers ---------------------------------------------------------------

SUPPLIER_TEXT_FIELDS = (
    "contact_person", "email", "phone", "alternate_phone", "website",
    "gstin", "pan_number", "tax_registration_type",
    "billing_address", "billing_city", "billing_state", "billing_state_code",
    "billing_postal_code", "billing_country",
    "shipping_address", "shipping_city", "shipping_state", "shipping_postal_code", "shipping_country",
    "bank_name", "bank_account_name", "bank_account_number", "bank_ifsc", "bank_branch",
    "notes",
)
SUPPLIER_UPPERCASE = {"gstin", "pan_number", "bank_ifsc"}
SUPPLIER_DEFAULTS = {
    "tax_registration_type": "registered",
    "billing_country": "India",
    "shipping_country": "India",
}


def _supplier_data(post, partial=False):
    """
    Cleaned supplier fields from a form post.
    partial=True (used for updates) only includes fields that were actually submitted.
    """
    data = {}
    for field in SUPPLIER_TEXT_FIELDS:
        if partial and field not in post:
            continue
        value = post.get(field, "").strip() or SUPPLIER_DEFAULTS.get(field, "")
        data[field] = value.upper() if field in SUPPLIER_UPPERCASE else value

    if not partial or "payment_terms_days" in post:
        data["payment_terms_days"] = int(dec(post.get("payment_terms_days"), "payment terms", "30"))
    if not partial or "credit_limit" in post:
        data["credit_limit"] = money(dec(post.get("credit_limit"), "credit limit"))
    if not partial or "opening_balance" in post:
        data["opening_balance"] = money(dec(post.get("opening_balance"), "opening balance"))
    return data


@require_POST
@finance_required
def supplier_create(request):
    try:
        with transaction.atomic():
            company = request.POST.get("company_name", "").strip()
            if not company:
                raise ValueError("Supplier company name is required.")

            code = (
                request.POST.get("supplier_code", "").strip()
                or f"SUP-{timezone.localdate():%y%m%d}-{secrets.token_hex(2).upper()}"
            )
            if Supplier.objects.filter(supplier_code=code).exists():
                raise ValueError("Supplier code already exists.")

            Supplier.objects.create(
                supplier_code=code,
                company_name=company,
                **_supplier_data(request.POST),
            )
        messages.success(request, "Supplier saved successfully.")

    except (ValueError, InvalidOperation) as exc:
        messages.error(request, str(exc))
    except Exception:
        logger.exception("Supplier creation failed")
        messages.error(request, "Could not save supplier. Check the server log.")

    return redirect("admin_index")


@require_POST
@finance_required
def supplier_update(request, supplier_id):
    supplier = get_object_or_404(Supplier, pk=supplier_id)

    try:
        company = request.POST.get("company_name", "").strip()
        if not company:
            raise ValueError("Supplier company name is required.")

        supplier.company_name = company
        for field, value in _supplier_data(request.POST, partial=True).items():
            setattr(supplier, field, value)
        supplier.save()
        messages.success(request, "Supplier updated successfully.")

    except (ValueError, InvalidOperation) as exc:
        messages.error(request, str(exc))

    return redirect("admin_index")


@require_POST
@finance_required
def supplier_toggle(request, supplier_id):
    supplier = get_object_or_404(Supplier, pk=supplier_id)
    supplier.is_active = not supplier.is_active
    supplier.save(update_fields=["is_active", "updated_at"])

    messages.success(
        request,
        f"{supplier.company_name} {'activated' if supplier.is_active else 'deactivated'}.",
    )
    return redirect("admin_index")


# ---- Purchase orders ----------------------------------------------------------

@require_POST
@finance_required
@transaction.atomic
def create_purchase_order(request):
    """Quick create: an empty PO for the chosen supplier, with the supplier's addresses snapshotted."""
    try:
        supplier = _active_supplier(request)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("purchases")

    order = PurchaseOrder(
        po_number=_temp_number("TEMPPO"),
        supplier=supplier,
        order_date=timezone.localdate(),
    )
    _snapshot_supplier(supplier, order)
    order.save()
    _finish_number(order, "UNPO", "po_number")

    messages.success(request, f"Purchase Order {order.po_number} created successfully.")
    return redirect("purchases")


@require_POST
@finance_required
def purchase_order_create(request):
    """Full create: PO header, product lines (existing or new products) and calculated totals."""
    try:
        with transaction.atomic():
            supplier = _active_supplier(request)

            status = request.POST.get("status", PurchaseOrder.Status.DRAFT)
            if status not in PurchaseOrder.Status.values:
                raise ValueError("Invalid purchase order status.")

            discount_type = request.POST.get("discount_type", "fixed")
            if discount_type not in ("fixed", "percent"):
                raise ValueError("Invalid order discount type.")

            discount_value = dec(request.POST.get("discount_value"), "order discount")
            shipping = dec(request.POST.get("shipping_cost"), "shipping cost")
            other = dec(request.POST.get("other_charges"), "other charges")
            adjustment = dec(request.POST.get("adjustment_amount"), "adjustment")

            if min(shipping, other, discount_value) < 0:
                raise ValueError("Discount, shipping and other charges cannot be negative.")
            if discount_type == "percent" and discount_value > 100:
                raise ValueError("Order discount cannot exceed 100%.")

            post = request.POST
            order = PurchaseOrder(
                po_number=_temp_number("TEMPPO"),
                supplier=supplier,
                order_date=post.get("order_date") or timezone.localdate(),
                expected_delivery_date=post.get("expected_delivery_date") or None,
                validity_date=post.get("validity_date") or None,
                status=status,
                reference_number=post.get("reference_number", "").strip(),
                destination_warehouse=post.get("destination_warehouse", "").strip(),
                delivery_method=post.get("delivery_method", "").strip(),
                place_of_supply=post.get("place_of_supply", "").strip(),
                is_interstate=post.get("is_interstate") == "true",
                prices_include_tax=post.get("prices_include_tax") == "true",
                currency=post.get("currency", "INR").strip().upper()[:3] or "INR",
                discount_type=discount_type,
                discount_value=discount_value,
                shipping_cost=shipping,
                other_charges=other,
                adjustment_amount=adjustment,
                terms_and_conditions=post.get("terms_and_conditions", "").strip(),
                internal_notes=post.get("internal_notes", "").strip(),
                supplier_notes=post.get("supplier_notes", "").strip(),
                created_by=str(request.session.get("admin")),
            )
            _snapshot_supplier(supplier, order)
            order.save()
            _finish_number(order, "UNPO", "po_number")

            product_ids = post.getlist("product_id[]")
            new_names = post.getlist("new_product_name[]")
            new_category_ids = post.getlist("new_product_category_id[]")
            quantities = post.getlist("quantity[]")
            prices = post.getlist("unit_price[]")
            discounts = post.getlist("discount_percent[]")
            gst_rates = post.getlist("gst_rate[]")
            descriptions = post.getlist("description[]")

            if not quantities or not (
                len(product_ids) == len(new_names) == len(new_category_ids)
                == len(quantities) == len(prices) == len(discounts) == len(gst_rates)
            ):
                raise ValueError("Purchase order line data is incomplete.")

            if len(descriptions) != len(quantities):
                descriptions = [""] * len(quantities)

            subtotal = line_discounts = taxable = cgst = sgst = igst = ZERO
            saved = 0
            category = None
            interstate = order.is_interstate

            for pid, new_name, new_cat_id, q_raw, p_raw, d_raw, g_raw, desc in zip(
                product_ids, new_names, new_category_ids, quantities, prices, discounts, gst_rates, descriptions
            ):
                if not pid and not new_name.strip():
                    continue

                # Existing product, or create a new one.
                if pid:
                    product = get_object_or_404(Product, pk=pid)
                else:
                    if new_cat_id:
                        category = get_object_or_404(Category, pk=new_cat_id)
                    elif category is None:
                        category = _product_category()
                    product = Product.objects.create(
                        category=category,
                        product_name=new_name.strip(),
                        price=money(dec(p_raw, "unit price")),
                        stock=0,
                        description=desc.strip() or "Created through purchasing",
                    )

                qty = dec(q_raw, "quantity")
                price = dec(p_raw, "unit price")
                disc = dec(d_raw, "line discount")
                gst = dec(g_raw, "GST rate")

                if qty <= 0 or price < 0 or not 0 <= disc <= 100 or not 0 <= gst <= 100:
                    raise ValueError(
                        f"Invalid quantity, price, discount or GST for {product.product_name}."
                    )

                # Line maths. When prices include tax, strip the tax out first so the
                # subtotal, discount and taxable value are all on the same (net) basis.
                base = qty * price
                if order.prices_include_tax and gst:
                    base = base / (1 + gst / 100)
                line_disc = base * disc / 100
                taxbase = base - line_disc
                line_tax = taxbase * gst / 100

                PurchaseOrderLine.objects.create(
                    purchase_order=order,
                    product=product,
                    description=desc.strip() or product.product_name,
                    quantity=qty,
                    unit_price=price,
                    discount_percent=disc,
                    gst_rate=gst,
                    cgst_rate=ZERO if interstate else gst / 2,
                    sgst_rate=ZERO if interstate else gst / 2,
                    igst_rate=gst if interstate else ZERO,
                )

                subtotal += base
                line_discounts += line_disc
                taxable += taxbase
                if interstate:
                    igst += line_tax
                else:
                    cgst += line_tax / 2
                    sgst += line_tax / 2
                saved += 1

            if not saved:
                raise ValueError("Add at least one product line.")

            order_discount = (
                taxable * discount_value / 100 if discount_type == "percent" else min(taxable, discount_value)
            )
            ratio = (taxable - order_discount) / taxable if taxable else ZERO

            order.subtotal = money(subtotal)
            order.discount_amount = money(line_discounts + order_discount)
            order.taxable_amount = money(taxable - order_discount)
            order.cgst_amount = money(cgst * ratio)
            order.sgst_amount = money(sgst * ratio)
            order.igst_amount = money(igst * ratio)
            order.total_tax = money(order.cgst_amount + order.sgst_amount + order.igst_amount)
            order.grand_total = money(order.taxable_amount + order.total_tax + shipping + other + adjustment)
            order.save()

        messages.success(request, f"Purchase order {order.po_number} created.")

    except (ValueError, InvalidOperation) as exc:
        messages.error(request, str(exc))
    except Exception:
        logger.exception("Purchase order creation failed")
        messages.error(request, "Could not create purchase order. Check your model fields and server log.")

    return redirect("admin_index")


def _change_po_status(request, po_id, redirect_to):
    """Shared status-change logic for purchase orders."""
    new_status = request.POST.get("status", "").strip()
    if new_status not in PurchaseOrder.Status.values:
        messages.error(request, "Invalid purchase order status.")
        return redirect(redirect_to)

    with transaction.atomic():
        order = get_object_or_404(PurchaseOrder.objects.select_for_update(), pk=po_id)

        if order.status == new_status:
            messages.info(request, f"{order.po_number} already has this status.")
            return redirect(redirect_to)

        if (
            new_status == PurchaseOrder.Status.RECEIVED
            and order.lines.filter(received_quantity__lt=F("quantity")).exists()
        ):
            messages.error(
                request,
                "Record all received quantities through Goods Receipt "
                "before marking this PO fully received.",
            )
            return redirect(redirect_to)

        order.status = new_status
        if new_status == PurchaseOrder.Status.APPROVED:
            order.approved_by = str(request.session.get("admin", "Admin"))
            order.approved_at = timezone.now()
        elif new_status == PurchaseOrder.Status.SENT:
            order.sent_at = timezone.now()
        elif new_status == PurchaseOrder.Status.CANCELLED:
            order.cancelled_at = timezone.now()
            order.cancellation_reason = request.POST.get("cancellation_reason", "").strip()
        order.save()

    messages.success(request, f"{order.po_number} updated to {order.get_status_display()}.")
    return redirect(redirect_to)


@require_POST
@finance_required
def update_purchase_status(request, po_id):
    """Status change from the Purchases page."""
    return _change_po_status(request, po_id, "purchases")


@require_POST
@finance_required
def purchase_order_status_update(request, po_id):
    """Status change from the dashboard modals."""
    return _change_po_status(request, po_id, "admin_index")


# ---- Goods receipts -----------------------------------------------------------

@require_POST
@finance_required
def goods_receipt_create(request):
    try:
        with transaction.atomic():
            order = get_object_or_404(
                PurchaseOrder.objects.select_for_update().select_related("supplier"),
                pk=request.POST.get("purchase_order"),
            )

            if order.status in (PurchaseOrder.Status.CANCELLED, PurchaseOrder.Status.CLOSED):
                raise ValueError("Cannot receive goods for a cancelled or closed purchase order.")

            post = request.POST
            line_ids = post.getlist("po_line_id[]")
            receiveds = post.getlist("quantity_received[]")
            accepteds = post.getlist("quantity_accepted[]")
            rejecteds = post.getlist("quantity_rejected[]")

            if not line_ids or not (len(line_ids) == len(receiveds) == len(accepteds) == len(rejecteds)):
                raise ValueError("Receipt line data is incomplete.")

            receipt = GoodsReceipt.objects.create(
                receipt_number=_temp_number("TEMPGR"),
                purchase_order=order,
                supplier=order.supplier,
                receipt_date=post.get("receipt_date") or timezone.localdate(),
                supplier_delivery_note=post.get("supplier_delivery_note", "").strip(),
                carrier_name=post.get("carrier_name", "").strip(),
                tracking_number=post.get("tracking_number", "").strip(),
                warehouse=post.get("warehouse", "").strip() or order.destination_warehouse,
                status=GoodsReceipt.Status.RECEIVED,
                received_by=str(request.session.get("admin")),
                inspection_notes=post.get("inspection_notes", "").strip(),
                internal_notes=post.get("internal_notes", "").strip(),
            )
            _finish_number(receipt, "UNGR", "receipt_number")

            received_any = False

            for line_id, r_raw, a_raw, rej_raw in zip(line_ids, receiveds, accepteds, rejecteds):
                line = get_object_or_404(
                    PurchaseOrderLine.objects.select_for_update().select_related("product"),
                    pk=line_id,
                    purchase_order=order,
                )

                r = dec(r_raw, "received quantity")
                a = dec(a_raw, "accepted quantity")
                rej = dec(rej_raw, "rejected quantity")

                if r == 0 and a == 0 and rej == 0:
                    continue
                if r <= 0 or a < 0 or rej < 0 or a + rej != r:
                    raise ValueError("Received quantity must equal accepted plus rejected quantity.")
                if line.received_quantity + r > line.quantity:
                    raise ValueError(
                        f"Received quantity exceeds remaining PO quantity for {line.product.product_name}."
                    )

                GoodsReceiptLine.objects.create(
                    receipt=receipt,
                    purchase_order_line=line,
                    quantity_received=r,
                    quantity_accepted=a,
                    quantity_rejected=rej,
                    rejection_reason=post.get(f"rejection_reason_{line_id}", "").strip(),
                )

                line.received_quantity += r
                line.save(update_fields=["received_quantity"])

                # Accepted goods go into stock (stock is a whole-number field).
                if a:
                    if a != a.to_integral_value():
                        raise ValueError(
                            f"Accepted quantity for {line.product.product_name} must be a whole number."
                        )
                    Product.objects.filter(pk=line.product_id).update(stock=F("stock") + int(a))

                received_any = True

            if not received_any:
                raise ValueError("Enter at least one received quantity.")

            lines = list(order.lines.all())
            if all(l.received_quantity >= l.quantity for l in lines):
                order.status = PurchaseOrder.Status.RECEIVED
            elif any(l.received_quantity > 0 for l in lines):
                order.status = PurchaseOrder.Status.PARTIAL
            order.save(update_fields=["status", "updated_at"])

        messages.success(request, f"Goods receipt {receipt.receipt_number} saved.")

    except (ValueError, InvalidOperation) as exc:
        messages.error(request, str(exc))
    except Exception:
        logger.exception("Goods receipt creation failed")
        messages.error(request, "Could not save goods receipt. Check the server log.")

    return redirect("admin_index")


# ---- Vendor bills ---------------------------------------------------------------

@require_POST
@finance_required
def vendor_bill_create(request):
    try:
        with transaction.atomic():
            post = request.POST
            supplier = _active_supplier(request)

            po_id = post.get("purchase_order") or None
            order = get_object_or_404(PurchaseOrder, pk=po_id, supplier=supplier) if po_id else None

            invoice_no = post.get("supplier_invoice_number", "").strip()
            if not invoice_no:
                raise ValueError("Supplier invoice number is required.")
            if VendorBill.objects.filter(supplier=supplier, supplier_invoice_number=invoice_no).exists():
                raise ValueError("This supplier invoice number already exists.")

            bill = VendorBill.objects.create(
                bill_number=_temp_number("TEMPBILL"),
                supplier=supplier,
                purchase_order=order,
                supplier_invoice_number=invoice_no,
                invoice_date=post.get("invoice_date") or timezone.localdate(),
                accounting_date=post.get("accounting_date") or timezone.localdate(),
                due_date=post.get("due_date") or None,
                status=VendorBill.Status.POSTED,
                currency=post.get("currency", "INR").strip().upper()[:3] or "INR",
                other_charges=money(dec(post.get("other_charges"), "other charges")),
                notes=post.get("notes", "").strip(),
                attachment=request.FILES.get("attachment"),
                created_by=str(request.session.get("admin")),
            )
            _finish_number(bill, "UNBILL", "bill_number")

            products = post.getlist("bill_product_id[]")
            quantities = post.getlist("bill_quantity[]")
            prices = post.getlist("bill_unit_price[]")
            discounts = post.getlist("bill_discount[]")
            cgsts = post.getlist("bill_cgst[]")
            sgsts = post.getlist("bill_sgst[]")
            igsts = post.getlist("bill_igst[]")
            po_lines = post.getlist("bill_po_line_id[]")

            arrays = [products, quantities, prices, discounts, cgsts, sgsts, igsts]
            if not products or len({len(x) for x in arrays}) != 1:
                raise ValueError("Vendor bill line data is incomplete.")

            subtotal = discount_total = taxable = cgst_total = sgst_total = igst_total = ZERO

            for i, (pid, qv, pv, dv, cv, sv, iv) in enumerate(zip(*arrays)):
                product = get_object_or_404(Product, pk=pid)

                qty = dec(qv, "bill quantity")
                price = dec(pv, "bill unit price")
                disc = dec(dv, "line discount")
                c = dec(cv, "CGST")
                s = dec(sv, "SGST")
                ig = dec(iv, "IGST")

                if qty <= 0 or price < 0 or min(disc, c, s, ig) < 0:
                    raise ValueError("Bill quantities and amounts must be valid.")

                line_sub = qty * price
                line_taxable = max(ZERO, line_sub - disc)
                line_total = line_taxable + c + s + ig

                po_line = None
                if i < len(po_lines) and po_lines[i]:
                    lookup = {"pk": po_lines[i], "product": product}
                    if order:
                        lookup["purchase_order"] = order
                    po_line = get_object_or_404(PurchaseOrderLine.objects.select_related("purchase_order"), **lookup)

                    if po_line.purchase_order.supplier_id != supplier.pk:
                        raise ValueError("Selected PO line does not belong to this supplier.")

                VendorBillLine.objects.create(
                    bill=bill,
                    product=product,
                    purchase_order_line=po_line,
                    description=product.product_name,
                    quantity=qty,
                    unit_price=price,
                    discount_amount=disc,
                    taxable_amount=line_taxable,
                    cgst_amount=c,
                    sgst_amount=s,
                    igst_amount=ig,
                    line_total=line_total,
                )

                subtotal += line_sub
                discount_total += disc
                taxable += line_taxable
                cgst_total += c
                sgst_total += s
                igst_total += ig

                if po_line:
                    po_line.billed_quantity += qty
                    po_line.save(update_fields=["billed_quantity"])

            bill.subtotal = money(subtotal)
            bill.discount_amount = money(discount_total)
            bill.taxable_amount = money(taxable)
            bill.cgst_amount = money(cgst_total)
            bill.sgst_amount = money(sgst_total)
            bill.igst_amount = money(igst_total)
            bill.grand_total = money(taxable + cgst_total + sgst_total + igst_total + bill.other_charges)
            bill.amount_paid = ZERO
            bill.amount_due = bill.grand_total
            bill.save()

            if order:
                _refresh_po_payment_status(order)

        messages.success(request, f"Vendor bill {bill.bill_number} posted.")

    except (ValueError, InvalidOperation) as exc:
        messages.error(request, str(exc))
    except Exception:
        logger.exception("Vendor bill creation failed")
        messages.error(request, "Could not save vendor bill. Check the server log.")

    return redirect("admin_index")


# ---- Vendor payments --------------------------------------------------------------

@require_POST
@finance_required
def vendor_payment_create(request):
    try:
        with transaction.atomic():
            post = request.POST
            supplier = _active_supplier(request)

            amount = money(dec(post.get("amount"), "payment amount"))
            if amount <= 0:
                raise ValueError("Payment amount must be greater than zero.")

            method = post.get("method", VendorPayment.Method.BANK)
            if method not in VendorPayment.Method.values:
                raise ValueError("Invalid payment method.")

            bill_ids = post.getlist("bill_id[]")
            alloc_raw = post.getlist("allocation_amount[]")
            if len(bill_ids) != len(alloc_raw):
                raise ValueError("Payment allocation data is incomplete.")

            allocations = []
            for bid, raw in zip(bill_ids, alloc_raw):
                if not bid:
                    continue

                bill = get_object_or_404(
                    VendorBill.objects.select_for_update(), pk=bid, supplier=supplier
                )
                alloc = money(dec(raw, "allocation amount"))
                if alloc <= 0:
                    continue

                if bill.status == VendorBill.Status.CANCELLED or alloc > bill.amount_due:
                    raise ValueError(f"Allocation exceeds the outstanding amount for {bill.bill_number}.")

                allocations.append((bill, alloc))

            if sum((a for _, a in allocations), ZERO) > amount:
                raise ValueError("Allocated amount cannot exceed payment amount.")

            payment = VendorPayment.objects.create(
                payment_number=_temp_number("TEMPPAY"),
                supplier=supplier,
                payment_date=post.get("payment_date") or timezone.localdate(),
                amount=amount,
                method=method,
                status=VendorPayment.Status.POSTED,
                transaction_reference=post.get("transaction_reference", "").strip(),
                bank_name=post.get("bank_name", "").strip(),
                cheque_number=post.get("cheque_number", "").strip(),
                notes=post.get("notes", "").strip(),
                created_by=str(request.session.get("admin")),
            )
            _finish_number(payment, "UNPAY", "payment_number")

            for bill, alloc in allocations:
                VendorPaymentAllocation.objects.create(payment=payment, bill=bill, amount_allocated=alloc)

                bill.amount_paid = money(bill.amount_paid + alloc)
                bill.amount_due = max(ZERO, money(bill.grand_total - bill.amount_paid))
                bill.status = VendorBill.Status.PAID if bill.amount_due == 0 else VendorBill.Status.PARTIAL
                bill.save(update_fields=["amount_paid", "amount_due", "status", "updated_at"])

                if bill.purchase_order_id:
                    _refresh_po_payment_status(bill.purchase_order)

        messages.success(request, f"Payment {payment.payment_number} recorded.")

    except (ValueError, InvalidOperation) as exc:
        messages.error(request, str(exc))
    except Exception:
        logger.exception("Vendor payment creation failed")
        messages.error(request, "Could not record vendor payment. Check the server log.")

    return redirect("admin_index")

# =============================================================================
# 11. ERP DESK APIs — separate datasets for each dashboard
# =============================================================================
from django.views.decorators.http import require_GET


@require_GET
def admin_desk_settlement(request):
    denied = _admin_or_401(request)
    if denied:
        return denied
    qs = Payment.objects.select_related("order").order_by("-created_at")
    paid = qs.filter(status="PAID")
    pending = qs.filter(status__in=["CREATED", "PENDING"])
    failed = qs.filter(status="FAILED")
    total_paid = paid.aggregate(v=Sum("amount"))["v"] or ZERO
    total_pending = pending.aggregate(v=Sum("amount"))["v"] or ZERO
    rows = [{
        "payment_id": p.razorpay_payment_id or "",
        "razorpay_order_id": p.razorpay_order_id,
        "order": p.order.order_number,
        "date": timezone.localtime(p.created_at).strftime("%d %b %Y"),
        "amount": _f(p.amount),
        "status": p.status,
    } for p in qs[:100]]
    return JsonResponse({
        "metrics": {
            "captured_amount": _f(total_paid),
            "captured_count": paid.count(),
            "pending_amount": _f(total_pending),
            "pending_count": pending.count(),
            "failed_count": failed.count(),
        },
        "settlement_status": "not_recorded",
        "message": "Razorpay settlement payouts, gateway fees and settlement dates are not stored in the current Payment model.",
        "payments": rows,
    })


# Indian state/UT names used to recover the delivery state from the current
# Order.shipping_address text snapshot. Longest names are checked first.
_INDIA_STATE_ALIASES = {
    "Andaman and Nicobar Islands": ("andaman and nicobar islands", "andaman & nicobar islands"),
    "Andhra Pradesh": ("andhra pradesh", "andhra"),
    "Arunachal Pradesh": ("arunachal pradesh",),
    "Assam": ("assam",),
    "Bihar": ("bihar",),
    "Chandigarh": ("chandigarh",),
    "Chhattisgarh": ("chhattisgarh", "chattisgarh"),
    "Dadra and Nagar Haveli and Daman and Diu": (
        "dadra and nagar haveli and daman and diu", "dadra and nagar haveli", "daman and diu"
    ),
    "Delhi": ("delhi", "new delhi"),
    "Goa": ("goa",),
    "Gujarat": ("gujarat",),
    "Haryana": ("haryana",),
    "Himachal Pradesh": ("himachal pradesh",),
    "Jammu and Kashmir": ("jammu and kashmir", "jammu & kashmir"),
    "Jharkhand": ("jharkhand",),
    "Karnataka": ("karnataka",),
    "Kerala": ("kerala",),
    "Ladakh": ("ladakh",),
    "Lakshadweep": ("lakshadweep",),
    "Madhya Pradesh": ("madhya pradesh",),
    "Maharashtra": ("maharashtra",),
    "Manipur": ("manipur",),
    "Meghalaya": ("meghalaya",),
    "Mizoram": ("mizoram",),
    "Nagaland": ("nagaland",),
    "Odisha": ("odisha", "orissa"),
    "Puducherry": ("puducherry", "pondicherry"),
    "Punjab": ("punjab",),
    "Rajasthan": ("rajasthan",),
    "Sikkim": ("sikkim",),
    "Tamil Nadu": ("tamil nadu",),
    "Telangana": ("telangana",),
    "Tripura": ("tripura",),
    "Uttar Pradesh": ("uttar pradesh",),
    "Uttarakhand": ("uttarakhand", "uttaranchal"),
    "West Bengal": ("west bengal",),
}


def _state_from_shipping_address(address):
    """Best-effort state extraction from the saved shipping-address snapshot."""
    value = " ".join(str(address or "").lower().replace("&", " and ").split())
    if not value:
        return "Unknown"
    candidates = sorted(
        ((alias, state) for state, aliases in _INDIA_STATE_ALIASES.items() for alias in aliases),
        key=lambda item: len(item[0]), reverse=True,
    )
    for alias, state in candidates:
        if re.search(r"(?<![a-z])" + re.escape(alias) + r"(?![a-z])", value):
            return state
    return "Unknown"


@require_GET
def admin_desk_rto(request):
    """List every RTO shipment and rank states by cancelled/returned COD orders."""
    denied = _admin_or_401(request)
    if denied:
        return denied

    shipments = ShiprocketShipment.objects.select_related("order", "order__customer").order_by("-updated_at")
    rto_shipments = shipments.filter(status__iexact="RTO")
    delivered = shipments.filter(status__iexact="DELIVERED")
    cancelled = Order.objects.filter(status__iexact="CANCELLED")

    # COD orders may remain COD_PENDING; Payment.status=PAID is not required.
    cod_orders = Order.objects.filter(payment_method__iexact="COD").order_by("-created_at")
    rto_order_ids = set(rto_shipments.values_list("order_id", flat=True))
    state_totals = defaultdict(lambda: {
        "state": "", "cod_orders": 0, "cancelled_cod": 0,
        "rto_cod": 0, "affected_cod": 0, "affected_value": ZERO,
    })
    unknown_state_orders = 0

    for order in cod_orders.iterator():
        state = _state_from_shipping_address(order.shipping_address)
        if state == "Unknown":
            unknown_state_orders += 1
        row = state_totals[state]
        row["state"] = state
        row["cod_orders"] += 1
        is_cancelled = (order.status or "").upper() == "CANCELLED"
        is_rto = order.id in rto_order_ids
        if is_cancelled:
            row["cancelled_cod"] += 1
        if is_rto:
            row["rto_cod"] += 1
        if is_cancelled or is_rto:
            row["affected_cod"] += 1
            row["affected_value"] += order.total_amount or ZERO

    state_rows = []
    for row in state_totals.values():
        row["affected_rate"] = round(row["affected_cod"] / row["cod_orders"] * 100, 2) if row["cod_orders"] else 0
        row["affected_value"] = _f(row["affected_value"])
        state_rows.append(row)
    state_rows.sort(key=lambda row: (-row["affected_cod"], -row["cod_orders"], row["state"]))

    # No [:100] limit: return the complete RTO shipment list.
    rto_rows = []
    for sh in rto_shipments:
        order = sh.order
        rto_rows.append({
            "order": order.order_number,
            "customer": getattr(order.customer, "name", "") if order.customer else "",
            "state": _state_from_shipping_address(order.shipping_address),
            "shipment_status": sh.status,
            "label": sh.current_status_label or sh.get_status_display(),
            "awb": sh.awb_code or "",
            "updated": timezone.localtime(sh.updated_at).strftime("%d %b %Y"),
            "tracking_url": sh.tracking_url or "",
            "amount": _f(order.total_amount or ZERO),
            "payment_method": getattr(order, "payment_method", "") or "",
        })

    total_shipments = shipments.count()
    top_state = state_rows[0] if state_rows else None
    return JsonResponse({
        "metrics": {
            "shipments": total_shipments,
            "rto_count": rto_shipments.count(),
            "delivered_count": delivered.count(),
            "cancelled_orders": cancelled.count(),
            "rto_rate": round(rto_shipments.count() / total_shipments * 100, 2) if total_shipments else 0,
            "rto_order_value": _f(sum((x.order.total_amount or ZERO for x in rto_shipments.select_related("order")), ZERO)),
            "cod_orders": cod_orders.count(),
            "cancelled_or_rto_cod": sum(row["affected_cod"] for row in state_rows),
            "unknown_state_orders": unknown_state_orders,
            "top_affected_cod_state": top_state["state"] if top_state else "—",
            "top_affected_cod_count": top_state["affected_cod"] if top_state else 0,
        },
        "state_wise_cod": state_rows,
        "rto_shipments": rto_rows,
        "refunds_recorded": False,
        "state_source": "State is extracted from the saved Order.shipping_address snapshot; unmatched addresses are grouped as Unknown.",
        "message": "State ranking counts COD orders that are cancelled or have an RTO Shiprocket shipment. The RTO list includes every shipment currently marked RTO.",
    })

@require_GET
def admin_desk_sales(request):
    denied = _admin_or_401(request)
    if denied:
        return denied
    orders = Order.objects.prefetch_related("items__product").order_by("-created_at")
    paid_orders = orders.filter(payments__status="PAID").distinct()
    paid_ids = list(paid_orders.values_list("id", flat=True))
    sales_orders = orders.filter(id__in=paid_ids).distinct()
    revenue = sales_orders.exclude(status__in=CANCELLED).aggregate(v=Sum("total_amount"))["v"] or ZERO
    count = sales_orders.exclude(status__in=CANCELLED).count()
    item_cost = ZERO
    product_cost_field = _ctx()["cost"]
    product_rows = []
    monthly = defaultdict(lambda: {"orders": 0, "revenue": ZERO, "cost": ZERO})
    for order in sales_orders:
        cancelled = (order.status or "").upper() in CANCELLED
        if cancelled:
            continue
        key = timezone.localtime(order.created_at).strftime("%Y-%m")
        monthly[key]["orders"] += 1
        monthly[key]["revenue"] += order.total_amount or ZERO
        for item in order.items.all():
            if product_cost_field:
                cost = getattr(item.product, product_cost_field, None)
                if cost is not None:
                    c = Decimal(str(cost)) * item.quantity
                    item_cost += c
                    monthly[key]["cost"] += c
    gross_profit = revenue - item_cost
    rows = [{
        "period": k,
        "orders": x["orders"],
        "revenue": _f(x["revenue"]),
        "cogs": _f(x["cost"]),
        "gross_profit": _f(x["revenue"] - x["cost"]),
    } for k, x in sorted(monthly.items())]
    return JsonResponse({
        "metrics": {
            "paid_orders": count,
            "net_revenue": _f(revenue),
            "recorded_cogs": _f(item_cost),
            "gross_profit_before_unrecorded_expenses": _f(gross_profit),
            "average_order_value": _f(revenue / count) if count else 0,
        },
        "monthly": rows,
        "ad_spend": None,
        "roas": None,
        "break_even_roas": None,
        "cost_field": product_cost_field,
        "message": "Advertising spend, gateway fees, shipping costs and fixed expenses are not recorded; ROAS and break-even ROAS cannot be calculated yet.",
    })


@require_GET
def admin_desk_stock(request):
    denied = _admin_or_401(request)
    if denied:
        return denied
    products = Product.objects.filter(is_archived=False).select_related("category").order_by("product_name")
    total_units = products.aggregate(v=Sum("stock"))["v"] or 0
    inventory_cost = ZERO
    cost_field = _ctx()["cost"]
    if cost_field:
        for p in products.only("stock", cost_field):
            cost = getattr(p, cost_field, None)
            if cost is not None:
                inventory_cost += Decimal(str(cost)) * p.stock
    receipts = GoodsReceipt.objects.select_related("supplier", "purchase_order").prefetch_related("lines__purchase_order_line__product").order_by("-receipt_date", "-id")
    batch_rows = []
    for receipt in receipts[:100]:
        for line in receipt.lines.all():
            pol = line.purchase_order_line
            batch_rows.append({
                "receipt": receipt.receipt_number,
                "date": receipt.receipt_date.isoformat(),
                "supplier": receipt.supplier.company_name,
                "product": pol.product.product_name,
                "batch": line.batch_number or "Not recorded",
                "received": _f(line.quantity_received),
                "accepted": _f(line.quantity_accepted),
                "rejected": _f(line.quantity_rejected),
                "unit_cost": _f(pol.unit_price),
                "batch_cost": _f(pol.unit_price * line.quantity_accepted),
            })
    product_rows = [{
        "product": p.product_name,
        "category": p.category.category_name,
        "stock": p.stock,
        "unit_cost": _f(getattr(p, cost_field)) if cost_field and getattr(p, cost_field, None) is not None else None,
        "stock_value": _f(Decimal(str(getattr(p, cost_field))) * p.stock) if cost_field and getattr(p, cost_field, None) is not None else None,
    } for p in products[:200]]
    return JsonResponse({
        "metrics": {
            "products": products.count(),
            "units_on_hand": total_units,
            "inventory_cost_value": _f(inventory_cost) if cost_field else None,
            "low_stock": products.filter(stock__gt=0, stock__lte=5).count(),
            "out_of_stock": products.filter(stock=0).count(),
            "goods_receipts": receipts.count(),
        },
        "cost_field": cost_field,
        "products": product_rows,
        "batches": batch_rows,
        "message": "Batch profitability is limited to goods-receipt quantities and PO unit prices. Batch-level sales allocation and full landed-cost allocation are not recorded.",
    })