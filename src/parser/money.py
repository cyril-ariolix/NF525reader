"""French decimal string to integer cents conversion."""

from decimal import Decimal, ROUND_HALF_UP


def parse_cents(value: str | None) -> int | None:
    """Parse a French-formatted monetary string into integer cents."""
    if value is None:
        return None

    text = value.strip()
    if not text:
        return None

    text = text.replace("\u00a0", "").replace(" ", "")

    negative = text.startswith("-")
    if negative:
        text = text[1:]

    if not text:
        return None

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")

    try:
        amount = Decimal(text).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return None

    cents = int(amount * 100)
    return -cents if negative else cents
