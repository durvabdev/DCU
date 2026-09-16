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


def next_account_id(existing_ids: list[str], prefix: str) -> str:
    max_suffix = 0
    for account_id in existing_ids:
        if not account_id.startswith(f"{prefix}-"):
            continue
        try:
            max_suffix = max(max_suffix, int(account_id.split("-", 1)[1]))
        except ValueError:
            continue
    return f"{prefix}-{max_suffix + 1:04d}"


def apply_balance_delta(balance: int, account_type: str, direction: str, amount_cents: int) -> int:
    """Apply a posted debit/credit using the same rules as seed data."""
    if account_type == "loan":
        return balance + amount_cents if direction == "debit" else balance - amount_cents
    return balance + amount_cents if direction == "credit" else balance - amount_cents


def next_transaction_id(existing_ids: list[str], account_id: str) -> str:
    prefix = f"TX-{account_id}-"
    max_suffix = 0
    for txn_id in existing_ids:
        if not txn_id.startswith(prefix):
            continue
        suffix = txn_id[len(prefix) :]
        try:
            max_suffix = max(max_suffix, int(suffix))
        except ValueError:
            continue
    return f"{prefix}{max_suffix + 1:04d}"
