from datetime import date
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

Money = Decimal

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class Invoice(StrictModel):
    invoice_id: str = Field(min_length=1)
    supplier: str = Field(min_length=1)
    invoice_date: date
    due_date: date | None = None
    amount: Money = Field(gt=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)

class Payment(StrictModel):
    payment_id: str = Field(min_length=1)
    invoice_id: str = Field(min_length=1)
    supplier: str = Field(min_length=1)
    payment_date: date
    amount: Money = Field(gt=0)
    reference: str | None = None

class BankTransaction(StrictModel):
    transaction_id: str = Field(min_length=1)
    transaction_date: date
    description: str = Field(min_length=1)
    counterparty: str | None = None
    amount: Money = Field(description="Outflow is negative, inflow is positive")
    reference: str | None = None

class ReconciliationRequest(StrictModel):
    invoices: list[Invoice]
    payments: list[Payment]
    bank_transactions: list[BankTransaction]

class ToolCall(StrictModel):
    tool: str
    input: dict
    result: str

class InvoiceResult(StrictModel):
    invoice_id: str
    supplier: str
    invoice_amount: Money
    paid_amount: Money
    outstanding_amount: Money
    status: Literal["paid", "partially_paid", "unpaid", "overpaid", "needs_review"]
    linked_payment_ids: list[str]
    linked_bank_transaction_ids: list[str]
    notes: list[str]

class Finding(StrictModel):
    finding_id: str
    category: str
    severity: Literal["info", "warning", "high"]
    summary: str
    evidence: list[str]
    recommendation: str
    requires_human_review: bool = True

class ReconciliationResponse(StrictModel):
    invoice_results: list[InvoiceResult]
    findings: list[Finding]
    summary: dict[str, int | str]
    agent_trace: list[ToolCall]
    disclaimer: str = "Synthetic-data prototype. Recommendations require human review; no accounting records are changed."
