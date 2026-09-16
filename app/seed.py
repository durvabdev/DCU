from __future__ import annotations

import argparse
import random
import sys
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal, drop_all, init_engine
from app.models import Account, Employee, InvestigationNote, Member, PortalSession, Transaction
from app.security import hash_password

DEMO_EMPLOYEES = [
    {
        "id": "EMP-100",
        "username": "j.patel",
        "password": "Willowbrook!25",
        "full_name": "Jordan Patel",
        "title": "Teller",
        "teller_id": "T-1001",
    },
    {
        "id": "EMP-200",
        "username": "m.okonkwo",
        "password": "Stoneharbor!31",
        "full_name": "Maya Okonkwo",
        "title": "Teller",
        "teller_id": "T-2001",
    },
]

MEMBERS = [
    {
        "id": "001234",
        "first_name": "Elena",
        "last_name": "Vargas",
        "email": "elena.vargas@example.com",
        "phone": "(602) 555-0142",
        "status": "active",
        "street": "1420 W Roosevelt St",
        "city": "Phoenix",
        "state": "AZ",
        "postal_code": "85007",
    },
    {
        "id": "001235",
        "first_name": "Elena",
        "last_name": "Varga",
        "email": "elena.varga@example.com",
        "phone": "(480) 555-0194",
        "status": "active",
        "street": "88 S Mill Ave",
        "city": "Tempe",
        "state": "AZ",
        "postal_code": "85281",
    },
    {
        "id": "002001",
        "first_name": "Marcus",
        "last_name": "Chen",
        "email": "marcus.chen@example.com",
        "phone": "(206) 555-0177",
        "status": "active",
        "street": "410 Occidental Ave S",
        "city": "Seattle",
        "state": "WA",
        "postal_code": "98104",
    },
    {
        "id": "002010",
        "first_name": "Priya",
        "last_name": "Nair",
        "email": "priya.nair@example.com",
        "phone": "(503) 555-0118",
        "status": "active",
        "street": "215 SW Morrison St",
        "city": "Portland",
        "state": "OR",
        "postal_code": "97204",
    },
    {
        "id": "003100",
        "first_name": "James",
        "last_name": "Okonkwo",
        "email": "james.okonkwo@example.com",
        "phone": "(713) 555-0160",
        "status": "active",
        "street": "910 Texas Ave",
        "city": "Houston",
        "state": "TX",
        "postal_code": "77002",
    },
    {
        "id": "003101",
        "first_name": "James",
        "last_name": "Okoye",
        "email": "james.okoye@example.com",
        "phone": "(214) 555-0133",
        "status": "active",
        "street": "300 N Akard St",
        "city": "Dallas",
        "state": "TX",
        "postal_code": "75201",
    },
    {
        "id": "004200",
        "first_name": "Sofia",
        "last_name": "Alvarez",
        "email": "sofia.alvarez@example.com",
        "phone": "(303) 555-0182",
        "status": "active",
        "street": "1600 Glenarm Pl",
        "city": "Denver",
        "state": "CO",
        "postal_code": "80202",
    },
    {
        "id": "005500",
        "first_name": "David",
        "last_name": "Kim",
        "email": "david.kim@example.com",
        "phone": "(312) 555-0106",
        "status": "active",
        "street": "233 S Wacker Dr",
        "city": "Chicago",
        "state": "IL",
        "postal_code": "60606",
    },
    {
        "id": "006600",
        "first_name": "Amina",
        "last_name": "Hassan",
        "email": "amina.hassan@example.com",
        "phone": "(404) 555-0155",
        "status": "active",
        "street": "275 Peachtree St NE",
        "city": "Atlanta",
        "state": "GA",
        "postal_code": "30303",
    },
    {
        "id": "007700",
        "first_name": "Robert",
        "last_name": "Walsh",
        "email": "robert.walsh@example.com",
        "phone": "(617) 555-0129",
        "status": "active",
        "street": "100 Federal St",
        "city": "Boston",
        "state": "MA",
        "postal_code": "02110",
    },
]

ACCOUNTS = [
    {"id": "CK-1001", "member_id": "001234", "account_type": "checking", "status": "active", "opening_cents": 421833},
    {"id": "LN-1001", "member_id": "001234", "account_type": "loan", "status": "active", "opening_cents": 1843250},
    {"id": "CK-1235", "member_id": "001235", "account_type": "checking", "status": "active", "opening_cents": 215040},
    {"id": "CK-2001", "member_id": "002001", "account_type": "checking", "status": "active", "opening_cents": 389250},
    {"id": "LN-2001", "member_id": "002001", "account_type": "loan", "status": "active", "opening_cents": 2214000},
    {"id": "CK-2010", "member_id": "002010", "account_type": "checking", "status": "active", "opening_cents": 612490},
    {"id": "SV-2010", "member_id": "002010", "account_type": "savings", "status": "active", "opening_cents": 1540000},
    {"id": "CK-3100", "member_id": "003100", "account_type": "checking", "status": "active", "opening_cents": 274880},
    {"id": "LN-3100", "member_id": "003100", "account_type": "loan", "status": "active", "opening_cents": 980000},
    {"id": "CK-3101", "member_id": "003101", "account_type": "checking", "status": "active", "opening_cents": 198765},
    {"id": "CK-4200", "member_id": "004200", "account_type": "checking", "status": "inactive", "opening_cents": 0},
    {"id": "SV-4200", "member_id": "004200", "account_type": "savings", "status": "active", "opening_cents": 875500},
    {"id": "SV-5500", "member_id": "005500", "account_type": "savings", "status": "active", "opening_cents": 1200000},
    {"id": "CK-5500", "member_id": "005500", "account_type": "checking", "status": "active", "opening_cents": 533210},
    {"id": "CK-6600", "member_id": "006600", "account_type": "checking", "status": "active", "opening_cents": 447120},
    {"id": "LN-6600", "member_id": "006600", "account_type": "loan", "status": "active", "opening_cents": 1632500},
    {"id": "CK-7700", "member_id": "007700", "account_type": "checking", "status": "active", "opening_cents": 309400},
]

TRANSACTION_COUNTS = {
    "CK-1001": 620,
    "LN-1001": 360,
    "CK-1235": 160,
    "CK-2001": 510,
    "LN-2001": 420,
    "CK-2010": 260,
    "SV-2010": 210,
    "CK-3100": 410,
    "LN-3100": 220,
    "CK-3101": 150,
    "CK-4200": 85,
    "SV-4200": 130,
    "SV-5500": 0,
    "CK-5500": 560,
    "CK-6600": 430,
    "LN-6600": 260,
    "CK-7700": 310,
}

DEPOSIT_DESCRIPTIONS = [
    "ACH payroll deposit",
    "Mobile check deposit",
    "ACH transfer in",
    "Interest credit",
    "Refund — merchant",
    "Wire credit",
]
WITHDRAWAL_DESCRIPTIONS = [
    "POS purchase — grocery",
    "POS purchase — fuel",
    "POS purchase — restaurant",
    "ATM withdrawal",
    "ACH bill pay",
    "Card purchase — pharmacy",
    "Card purchase — online retail",
    "Utility payment",
]
SAVINGS_CREDIT = ["Interest credit", "Transfer from checking", "Payroll sweep"]
SAVINGS_DEBIT = ["Transfer to checking", "Scheduled savings withdrawal"]
LOAN_DEBIT = ["Principal advance", "Interest charge", "Loan draw"]
LOAN_CREDIT = ["Loan payment", "Principal payment", "Automatic payment"]

FIXTURE_TRANSACTIONS = [
    {
        "id": "TX-LN-1001-F01",
        "account_id": "LN-1001",
        "posted_on": date(2026, 1, 15),
        "description": "FIXTURE below $500.00 debit — January 2026",
        "amount_cents": 25000,
        "direction": "debit",
        "status": "posted",
        "currency": "USD",
    },
    {
        "id": "TX-LN-1001-F02",
        "account_id": "LN-1001",
        "posted_on": date(2026, 1, 20),
        "description": "FIXTURE exact $500.00 debit — January 2026",
        "amount_cents": 50000,
        "direction": "debit",
        "status": "posted",
        "currency": "USD",
    },
    {
        "id": "TX-LN-1001-F03",
        "account_id": "LN-1001",
        "posted_on": date(2026, 1, 25),
        "description": "FIXTURE above $500.00 credit — January 2026",
        "amount_cents": 75000,
        "direction": "credit",
        "status": "posted",
        "currency": "USD",
    },
    {
        "id": "TX-LN-1001-F04",
        "account_id": "LN-1001",
        "posted_on": date(2026, 1, 5),
        "description": "FIXTURE $499.99 debit — January 2026",
        "amount_cents": 49999,
        "direction": "debit",
        "status": "posted",
        "currency": "USD",
    },
    {
        "id": "TX-LN-1001-F05",
        "account_id": "LN-1001",
        "posted_on": date(2025, 12, 15),
        "description": "FIXTURE $500.01 credit — outside January 2026",
        "amount_cents": 50001,
        "direction": "credit",
        "status": "posted",
        "currency": "USD",
    },
    {
        "id": "TX-LN-1001-F06",
        "account_id": "LN-1001",
        "posted_on": date(2026, 2, 1),
        "description": "FIXTURE $100.00 debit — outside January 2026",
        "amount_cents": 10000,
        "direction": "debit",
        "status": "posted",
        "currency": "USD",
    },
    {
        "id": "TX-LN-1001-F07",
        "account_id": "LN-1001",
        "posted_on": date(2026, 1, 10),
        "description": "FIXTURE $1,200.00 debit — January 2026",
        "amount_cents": 120000,
        "direction": "debit",
        "status": "posted",
        "currency": "USD",
    },
]

SEED_NOTES = [
    {
        "id": "NT-SEED-001",
        "transaction_id": "TX-LN-1001-F02",
        "author_id": "EMP-100",
        "body": "Reviewed the exact $500.00 January posting during the cycle audit. Amount matches the member's scheduled loan payment.",
        "category": "general review",
        "created_at": datetime(2026, 1, 21, 14, 32, tzinfo=timezone.utc),
        "idempotency_token": "seed-note-001",
    },
    {
        "id": "NT-SEED-002",
        "transaction_id": "TX-LN-1001-F07",
        "author_id": "EMP-200",
        "body": "Member asked about the $1,200.00 January advance. Follow up if a duplicate draw posts.",
        "category": "follow-up required",
        "created_at": datetime(2026, 1, 11, 9, 5, tzinfo=timezone.utc),
        "idempotency_token": "seed-note-002",
    },
    {
        "id": "NT-SEED-003",
        "transaction_id": "TX-LN-1001-F03",
        "author_id": "EMP-100",
        "body": "Credit above $500.00 confirmed as an extra principal payment in January 2026.",
        "category": "customer explanation",
        "created_at": datetime(2026, 1, 26, 16, 18, tzinfo=timezone.utc),
        "idempotency_token": "seed-note-003",
    },
]

RNG_SEED = 20260914


def print_demo_credentials() -> None:
    print("Demo employee logins (local only — not stored in documentation):")
    for employee in DEMO_EMPLOYEES:
        print(f"  username: {employee['username']}")
        print(f"  password: {employee['password']}")


def _apply_amount(balance: int, account_type: str, direction: str, amount_cents: int) -> int:
    if account_type == "loan":
        return balance + amount_cents if direction == "debit" else balance - amount_cents
    return balance + amount_cents if direction == "credit" else balance - amount_cents


def _generate_transactions() -> tuple[list[dict], dict[str, int]]:
    rng = random.Random(RNG_SEED)
    account_types = {row["id"]: row["account_type"] for row in ACCOUNTS}
    balances = {row["id"]: row["opening_cents"] for row in ACCOUNTS}
    rows: list[dict] = []

    for account in ACCOUNTS:
        account_id = account["id"]
        count = TRANSACTION_COUNTS[account_id]
        account_type = account["account_type"]
        if account_id == "CK-4200":
            start, end = date(2023, 3, 1), date(2024, 8, 31)
        else:
            start, end = date(2024, 6, 1), date(2026, 8, 31)
        span = (end - start).days
        for seq in range(1, count + 1):
            if account_type == "loan":
                direction = "credit" if rng.random() < 0.72 else "debit"
                description = rng.choice(LOAN_CREDIT if direction == "credit" else LOAN_DEBIT)
                amount_cents = rng.choice(
                    [2500, 5000, 7500, 10000, 12500, 15000, 20000, 25000, 35000, 45000, 50000]
                )
                if rng.random() < 0.08:
                    amount_cents = rng.randint(51000, 180000)
            elif account_type == "savings":
                direction = "credit" if rng.random() < 0.65 else "debit"
                description = rng.choice(SAVINGS_CREDIT if direction == "credit" else SAVINGS_DEBIT)
                amount_cents = rng.choice([2500, 5000, 10000, 20000, 50000, 75000, 100000])
            else:
                direction = "debit" if rng.random() < 0.62 else "credit"
                description = rng.choice(
                    WITHDRAWAL_DESCRIPTIONS if direction == "debit" else DEPOSIT_DESCRIPTIONS
                )
                amount_cents = rng.randint(325, 18500)
                if direction == "credit" and rng.random() < 0.2:
                    amount_cents = rng.choice([125000, 185000, 210000, 245000])
                    description = "ACH payroll deposit"

            proposed = _apply_amount(balances[account_id], account_type, direction, amount_cents)
            if proposed < 0:
                direction = "credit" if account_type != "loan" else "debit"
                if account_type == "loan":
                    description = rng.choice(LOAN_DEBIT)
                elif account_type == "savings":
                    description = rng.choice(SAVINGS_CREDIT)
                else:
                    description = rng.choice(DEPOSIT_DESCRIPTIONS)
                proposed = _apply_amount(balances[account_id], account_type, direction, amount_cents)

            balances[account_id] = proposed
            posted_on = start + timedelta(days=rng.randint(0, span))
            # Sprinkle January 2026 activity on busy loan/checking accounts.
            if account_id in {"LN-1001", "CK-1001", "LN-2001"} and seq % 17 == 0:
                posted_on = date(2026, 1, rng.randint(1, 31))
            rows.append(
                {
                    "id": f"TX-{account_id}-{seq:04d}",
                    "account_id": account_id,
                    "posted_on": posted_on,
                    "description": description,
                    "amount_cents": amount_cents,
                    "direction": direction,
                    "status": "posted",
                    "currency": "USD",
                }
            )

    for fixture in FIXTURE_TRANSACTIONS:
        rows.append(dict(fixture))
        balances[fixture["account_id"]] = _apply_amount(
            balances[fixture["account_id"]],
            account_types[fixture["account_id"]],
            fixture["direction"],
            fixture["amount_cents"],
        )

    return rows, balances


def seed_database(db: Session) -> None:
    employees = []
    for row in DEMO_EMPLOYEES:
        employees.append(
            Employee(
                id=row["id"],
                username=row["username"],
                password_hash=hash_password(row["password"]),
                full_name=row["full_name"],
                title=row["title"],
                teller_id=row["teller_id"],
            )
        )
    db.add_all(employees)
    db.add_all([Member(**row) for row in MEMBERS])
    db.flush()

    txn_rows, balances = _generate_transactions()
    accounts = []
    for row in ACCOUNTS:
        accounts.append(
            Account(
                id=row["id"],
                member_id=row["member_id"],
                account_type=row["account_type"],
                status=row["status"],
                currency="USD",
                balance_cents=balances[row["id"]],
            )
        )
    db.add_all(accounts)
    db.flush()
    db.execute(insert(Transaction), txn_rows)
    db.add_all([InvestigationNote(**row) for row in SEED_NOTES])
    db.flush()


def is_seeded(db: Session) -> bool:
    count = db.scalar(select(func.count()).select_from(Employee))
    return bool(count)


def reset_database(keep_session: dict | None = None) -> None:
    drop_all()
    db = SessionLocal()
    try:
        seed_database(db)
        db.query(PortalSession).delete()
        if keep_session:
            from app.security import default_flags
            import json

            db.add(
                PortalSession(
                    id=keep_session["id"],
                    employee_id=keep_session["employee_id"],
                    csrf_token=keep_session["csrf_token"],
                    created_at=keep_session["created_at"],
                    expires_at=keep_session["expires_at"],
                    flags_json=json.dumps(default_flags()),
                )
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def reset_with_session(db: Session, keep_session: PortalSession | None = None) -> PortalSession | None:
    """Wipe demonstration rows using the current SQLAlchemy session, then reseed."""
    snapshot = None
    if keep_session is not None:
        snapshot = {
            "id": keep_session.id,
            "employee_id": keep_session.employee_id,
            "csrf_token": keep_session.csrf_token,
            "created_at": keep_session.created_at,
            "expires_at": keep_session.expires_at,
        }
    db.query(InvestigationNote).delete()
    db.query(Transaction).delete()
    db.query(Account).delete()
    db.query(Member).delete()
    db.query(PortalSession).delete()
    db.query(Employee).delete()
    db.flush()
    seed_database(db)
    preserved = None
    if snapshot is not None:
        from app.security import default_flags
        import json

        preserved = PortalSession(
            id=snapshot["id"],
            employee_id=snapshot["employee_id"],
            csrf_token=snapshot["csrf_token"],
            created_at=snapshot["created_at"],
            expires_at=snapshot["expires_at"],
            flags_json=json.dumps(default_flags()),
        )
        db.add(preserved)
        db.flush()
    return preserved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the Dough Credit Union Member Services Portal database.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Wipe local demonstration data and restore the deterministic seed.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Do not print demo usernames or passwords.",
    )
    args = parser.parse_args(argv)
    settings = get_settings()
    init_engine(settings.database_url)
    db = SessionLocal()
    try:
        if args.reset:
            db.close()
            reset_database()
            print("Database reset and re-seeded.")
            if not args.quiet:
                print_demo_credentials()
            return 0
        if is_seeded(db):
            print("Database already seeded. Use --reset to wipe demonstration data and restore the seed.")
            if not args.quiet:
                print_demo_credentials()
            return 0
        seed_database(db)
        db.commit()
        print("Database seeded.")
        if not args.quiet:
            print_demo_credentials()
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        if db.is_active:
            db.close()


if __name__ == "__main__":
    sys.exit(main())
