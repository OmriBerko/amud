"""Hebrew RTL UI for business details, customers, quotes, and tax invoices."""

import re
from datetime import datetime
from decimal import InvalidOperation
from urllib.parse import quote

from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from markupsafe import Markup, escape

from .db import get_db, get_settings, next_number
from .money import VAT_PERCENT, document_totals, format_nis, format_qty, line_amount, parse_decimal
from .pdf import DOC_TITLES, render_document_pdf

bp = Blueprint("main", __name__)

DOC_TYPES = ("quote", "tax_invoice")
LABELS = ("ח.פ.", "ע.מ.")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _format_date(iso: str) -> str:
    year, month, day = iso.split("-")
    return f"{day}/{month}/{year}"


def _ltr(value) -> Markup:
    if value is None or value == "":
        return Markup("")
    return Markup(f'<bdi dir="ltr">{escape(value)}</bdi>')


# Latin letters and digits stay left-to-right inside a Hebrew sentence.
_LTR_RUN = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9&+./:#@_%\-]|[ \t]+(?=[A-Za-z0-9]))*"
)


def _mixed(value) -> Markup:
    if value is None or value == "":
        return Markup("")
    raw = str(value)
    parts = []
    last = 0
    for match in _LTR_RUN.finditer(raw):
        parts.append(str(escape(raw[last:match.start()])))
        parts.append(f'<bdi dir="ltr">{escape(match.group())}</bdi>')
        last = match.end()
    parts.append(str(escape(raw[last:])))
    return Markup("".join(parts))


def _nis(value) -> Markup:
    return _ltr(format_nis(value))


def _load_document(db, doc_id: int):
    doc = db.execute(
        """
        SELECT d.*,
               c.name AS customer_name,
               c.address AS customer_address,
               c.id_number AS customer_id_number
        FROM documents d
        JOIN customers c ON c.id = d.customer_id
        WHERE d.id = ?
        """,
        (doc_id,),
    ).fetchone()
    if doc is None:
        return None
    rows = db.execute(
        """
        SELECT description, quantity, unit_price
        FROM line_items
        WHERE document_id = ?
        ORDER BY position, id
        """,
        (doc_id,),
    ).fetchall()
    lines = []
    for row in rows:
        amount = line_amount(row["quantity"], row["unit_price"])
        lines.append(
            {
                "description": row["description"],
                "quantity": row["quantity"],
                "unit_price": row["unit_price"],
                "quantity_display": format_qty(row["quantity"]),
                "unit_price_display": format_nis(row["unit_price"]),
                "amount": amount,
                "amount_display": format_nis(amount),
            }
        )
    totals = document_totals(lines, doc["vat_percent"])
    settings = get_settings(db)
    return {
        "id": doc["id"],
        "doc_type": doc["doc_type"],
        "title": DOC_TITLES[doc["doc_type"]],
        "number": doc["number"],
        "number_display": f"{doc['number']:04d}",
        "issue_date": doc["issue_date"],
        "issue_date_display": _format_date(doc["issue_date"]),
        "allocation_number": doc["allocation_number"] or "",
        "notes": doc["notes"] or "",
        "customer": {
            "name": doc["customer_name"],
            "address": doc["customer_address"],
            "id_number": doc["customer_id_number"],
        },
        "business": None
        if settings is None
        else {
            "name": settings["business_name"],
            "address": settings["address"],
            "company_number": settings["company_number"],
            "company_number_label": settings["company_number_label"],
            "phone": settings["phone"],
        },
        "lines": lines,
        "totals": totals,
        "created_at": doc["created_at"],
    }


def _parse_lines(form):
    descriptions = form.getlist("description")
    quantities = form.getlist("quantity")
    prices = form.getlist("unit_price")
    count = max(len(descriptions), len(quantities), len(prices), 0)
    rows = []
    errors = []
    for index in range(count):
        description = (descriptions[index] if index < len(descriptions) else "").strip()
        quantity_raw = (quantities[index] if index < len(quantities) else "").strip()
        price_raw = (prices[index] if index < len(prices) else "").strip()
        if not description and not quantity_raw and not price_raw:
            continue
        display = {
            "description": description,
            "quantity": quantity_raw,
            "unit_price": price_raw,
        }
        if not description:
            errors.append(f"שורה {len(rows) + 1}: חסר תיאור.")
            rows.append(display)
            continue
        try:
            quantity = parse_decimal(quantity_raw)
            unit_price = parse_decimal(price_raw)
        except (InvalidOperation, ValueError):
            errors.append(f"שורה {len(rows) + 1}: כמות או מחיר אינם מספר.")
            rows.append(display)
            continue
        if quantity <= 0:
            errors.append(f"שורה {len(rows) + 1}: הכמות חייבת להיות גדולה מאפס.")
        if unit_price < 0:
            errors.append(f"שורה {len(rows) + 1}: המחיר אינו יכול להיות שלילי.")
        display["quantity"] = format_qty(quantity)
        display["unit_price"] = format(unit_price, "f")
        rows.append(display)
    if not rows:
        errors.append("יש להוסיף לפחות שורת פריט אחת.")
    return rows, errors


@bp.route("/")
def home():
    return redirect(url_for("main.documents"))


@bp.route("/settings", methods=["GET", "POST"])
def settings():
    db = get_db()
    current = get_settings(db)
    if request.method == "POST":
        business_name = request.form.get("business_name", "").strip()
        address = request.form.get("address", "").strip()
        company_number = request.form.get("company_number", "").strip()
        label = request.form.get("company_number_label", "").strip()
        phone = request.form.get("phone", "").strip()
        errors = []
        if not business_name:
            errors.append("חסר שם העסק.")
        if not address:
            errors.append("חסרה כתובת.")
        if not company_number:
            errors.append("חסר מספר ח.פ. או ע.מ.")
        if label not in LABELS:
            errors.append("יש לבחור ח.פ. או ע.מ.")
        if not phone:
            errors.append("חסר טלפון.")
        if errors:
            for message in errors:
                flash(message, "error")
            current = {
                "business_name": business_name,
                "address": address,
                "company_number": company_number,
                "company_number_label": label if label in LABELS else "ח.פ.",
                "phone": phone,
            }
        else:
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute(
                    """
                    INSERT INTO settings (
                        id, business_name, address, company_number,
                        company_number_label, phone
                    ) VALUES (1, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        business_name = excluded.business_name,
                        address = excluded.address,
                        company_number = excluded.company_number,
                        company_number_label = excluded.company_number_label,
                        phone = excluded.phone
                    """,
                    (business_name, address, company_number, label, phone),
                )
                db.commit()
            except Exception:
                db.rollback()
                raise
            flash("פרטי העסק נשמרו.", "ok")
            return redirect(url_for("main.settings"))
    return render_template("settings.html", settings=current, labels=LABELS)


@bp.route("/customers", methods=["GET", "POST"])
def customers():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        address = request.form.get("address", "").strip()
        id_number = request.form.get("id_number", "").strip()
        if not name:
            flash("חסר שם לקוח.", "error")
        else:
            db.execute(
                """
                INSERT INTO customers (name, address, id_number, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (name, address, id_number, _now()),
            )
            flash("הלקוח נשמר.", "ok")
            return redirect(url_for("main.customers"))
    rows = db.execute(
        "SELECT * FROM customers ORDER BY name COLLATE NOCASE, id"
    ).fetchall()
    return render_template("customers.html", customers=rows)


@bp.route("/documents")
def documents():
    db = get_db()
    settings = get_settings(db)
    rows = db.execute(
        """
        SELECT d.id, d.doc_type, d.number, d.issue_date, d.vat_percent,
               c.name AS customer_name
        FROM documents d
        JOIN customers c ON c.id = d.customer_id
        ORDER BY d.id DESC
        """
    ).fetchall()
    listing = []
    for row in rows:
        payload = _load_document(db, row["id"])
        listing.append(payload)
    return render_template(
        "documents.html",
        documents=listing,
        has_settings=settings is not None,
        titles=DOC_TITLES,
    )


@bp.route("/documents/new", methods=["GET", "POST"])
def new_document():
    db = get_db()
    settings = get_settings(db)
    if settings is None:
        flash("לפני מסמך ראשון יש לשמור את פרטי העסק.", "error")
        return redirect(url_for("main.settings"))
    customers = db.execute(
        "SELECT id, name FROM customers ORDER BY name COLLATE NOCASE, id"
    ).fetchall()
    if not customers:
        flash("לפני מסמך יש להוסיף לקוח.", "error")
        return redirect(url_for("main.customers"))

    requested = request.values.get("doc_type", "quote")
    if requested not in DOC_TYPES:
        requested = "quote"
    form = {
        "doc_type": requested,
        "customer_id": request.values.get("customer_id", ""),
        "issue_date": request.values.get("issue_date", _today()),
        "allocation_number": request.values.get("allocation_number", ""),
        "notes": request.values.get("notes", ""),
        "lines": [{"description": "", "quantity": "1", "unit_price": ""}],
    }
    if request.method == "POST":
        form["doc_type"] = request.form.get("doc_type", "quote").strip()
        form["customer_id"] = request.form.get("customer_id", "").strip()
        form["issue_date"] = request.form.get("issue_date", "").strip()
        form["allocation_number"] = request.form.get("allocation_number", "").strip()
        form["notes"] = request.form.get("notes", "").strip()
        lines, errors = _parse_lines(request.form)
        form["lines"] = lines or form["lines"]
        if form["doc_type"] not in DOC_TYPES:
            errors.append("סוג מסמך לא מוכר.")
        customer = db.execute(
            "SELECT id FROM customers WHERE id = ?", (form["customer_id"],)
        ).fetchone()
        if customer is None:
            errors.append("יש לבחור לקוח.")
        try:
            parsed_date = datetime.strptime(form["issue_date"], "%Y-%m-%d")
            form["issue_date"] = parsed_date.strftime("%Y-%m-%d")
        except ValueError:
            errors.append("תאריך אינו תקין.")
        if errors:
            for message in errors:
                flash(message, "error")
        else:
            db.execute("BEGIN IMMEDIATE")
            try:
                number = next_number(db, form["doc_type"])
                cursor = db.execute(
                    """
                    INSERT INTO documents (
                        doc_type, number, customer_id, issue_date,
                        allocation_number, notes, vat_percent, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        form["doc_type"],
                        number,
                        int(form["customer_id"]),
                        form["issue_date"],
                        form["allocation_number"] or None,
                        form["notes"] or None,
                        format(VAT_PERCENT, "f"),
                        _now(),
                    ),
                )
                doc_id = cursor.lastrowid
                for position, line in enumerate(lines, start=1):
                    db.execute(
                        """
                        INSERT INTO line_items (
                            document_id, position, description, quantity, unit_price
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            doc_id,
                            position,
                            line["description"],
                            str(parse_decimal(line["quantity"])),
                            str(parse_decimal(line["unit_price"])),
                        ),
                    )
                db.commit()
            except Exception:
                db.rollback()
                raise
            flash(f"{DOC_TITLES[form['doc_type']]} {number:04d} נשמרה.", "ok")
            return redirect(url_for("main.document_detail", doc_id=doc_id))

    next_numbers = {kind: next_number(db, kind) for kind in DOC_TYPES}
    return render_template(
        "document_form.html",
        form=form,
        customers=customers,
        titles=DOC_TITLES,
        next_numbers=next_numbers,
        vat_percent=format(VAT_PERCENT, "f"),
    )


@bp.route("/documents/<int:doc_id>")
def document_detail(doc_id):
    payload = _load_document(get_db(), doc_id)
    if payload is None:
        abort(404)
    return render_template("document_detail.html", doc=payload)


@bp.route("/documents/<int:doc_id>/pdf")
def document_pdf(doc_id):
    db = get_db()
    payload = _load_document(db, doc_id)
    if payload is None:
        abort(404)
    if payload["business"] is None:
        flash("לא ניתן להפיק PDF בלי פרטי העסק.", "error")
        return redirect(url_for("main.settings"))
    pdf = render_document_pdf(payload)
    ascii_name = f"amud-{payload['doc_type']}-{payload['number_display']}.pdf"
    hebrew_name = f"{payload['title']}-{payload['number_display']}.pdf"
    response = current_app_response(pdf)
    response.headers["Content-Disposition"] = (
        f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(hebrew_name)}"
    )
    return response


def current_app_response(pdf: bytes):
    return Response(pdf, mimetype="application/pdf")


def register_template_helpers(app):
    app.add_template_filter(_ltr, "ltr")
    app.add_template_filter(_mixed, "mixed")
    app.add_template_filter(_nis, "nis")
    app.add_template_filter(
        lambda value: Markup(escape(format_qty(value))) if value not in (None, "") else Markup(""),
        "qty",
    )
