from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

NOTE_CATEGORIES = (
    "general review",
    "customer explanation",
    "follow-up required",
)

PAGE_SIZE = 10


def format_money(cents: int) -> str:
    negative = cents < 0
    cents = abs(cents)
    value = f"${cents // 100:,}.{cents % 100:02d}"
    return f"-{value}" if negative else value


def format_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_date(raw: str | None) -> date | None:
    if not raw or not raw.strip():
        return None
    return date.fromisoformat(raw.strip())


def parse_amount_to_cents(raw: str) -> int:
    cleaned = raw.strip().replace("$", "").replace(",", "")
    if not cleaned:
        raise ValueError("empty amount")
    amount = Decimal(cleaned)
    cents = amount * 100
    if cents != cents.to_integral_value():
        raise InvalidOperation("too many decimal places")
    return int(cents)
