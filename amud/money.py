"""NIS amounts as Decimal agorot, never binary floats."""

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

CENT = Decimal("0.01")
VAT_PERCENT = Decimal("18")


def parse_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    text = str(value).strip().replace("₪", "").replace(" ", "").replace("\u00a0", "")
    if not text:
        raise InvalidOperation("empty amount")
    if text.count(",") == 1 and "." not in text:
        text = text.replace(",", ".")
    else:
        text = text.replace(",", "")
    return Decimal(text)


def money(value) -> Decimal:
    return parse_decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def line_amount(quantity, unit_price) -> Decimal:
    return (parse_decimal(quantity) * parse_decimal(unit_price)).quantize(
        CENT, rounding=ROUND_HALF_UP
    )


def document_totals(lines, vat_percent=VAT_PERCENT):
    subtotal = sum(
        (line_amount(line["quantity"], line["unit_price"]) for line in lines),
        Decimal("0.00"),
    )
    rate = parse_decimal(vat_percent)
    vat = (subtotal * rate / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)
    return {
        "subtotal": subtotal,
        "vat": vat,
        "total": (subtotal + vat).quantize(CENT, rounding=ROUND_HALF_UP),
        "vat_percent": rate,
    }


def format_nis(value) -> str:
    amount = money(value)
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    whole, frac = f"{amount:.2f}".split(".")
    groups = []
    while whole:
        groups.append(whole[-3:])
        whole = whole[:-3]
    return f"{sign}₪{','.join(reversed(groups))}.{frac}"


def format_qty(value) -> str:
    amount = parse_decimal(value)
    text = format(amount, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"
