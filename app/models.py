from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    full_name: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    teller_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)

    notes: Mapped[list[InvestigationNote]] = relationship(back_populates="author")


class Member(Base):
    __tablename__ = "members"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    first_name: Mapped[str] = mapped_column(String(64), nullable=False)
    last_name: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[str] = mapped_column(String(128), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    street: Mapped[str] = mapped_column(String(128), nullable=False)
    city: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    postal_code: Mapped[str] = mapped_column(String(16), nullable=False)

    accounts: Mapped[list[Account]] = relationship(back_populates="member")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    member_id: Mapped[str] = mapped_column(String(16), ForeignKey("members.id"), nullable=False)
    account_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    balance_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    member: Mapped[Member] = relationship(back_populates="accounts")
    transactions: Mapped[list[Transaction]] = relationship(back_populates="account")

    @property
    def type_label(self) -> str:
        return {
            "checking": "Checking",
            "savings": "Savings",
            "loan": "Loan",
        }.get(self.account_type, self.account_type.title())

    @property
    def balance_label(self) -> str:
        if self.account_type == "loan":
            return "Outstanding balance"
        return "Current balance"


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_txn_account_posted", "account_id", "posted_on"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(16), ForeignKey("accounts.id"), nullable=False)
    posted_on: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="posted")
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")

    account: Mapped[Account] = relationship(back_populates="transactions")
    notes: Mapped[list[InvestigationNote]] = relationship(back_populates="transaction")


class InvestigationNote(Base):
    __tablename__ = "investigation_notes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    transaction_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("transactions.id"), nullable=False
    )
    author_id: Mapped[str] = mapped_column(String(32), ForeignKey("employees.id"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idempotency_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    transaction: Mapped[Transaction] = relationship(back_populates="notes")
    author: Mapped[Employee] = relationship(back_populates="notes")


class PortalSession(Base):
    __tablename__ = "portal_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    employee_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("employees.id"), nullable=True
    )
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    flags_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    employee: Mapped[Employee | None] = relationship()
