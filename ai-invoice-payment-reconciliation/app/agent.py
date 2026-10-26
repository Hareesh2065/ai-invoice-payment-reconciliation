"""Transparent tool-using investigation workflow (no LLM required in starter)."""
from collections import defaultdict
from decimal import Decimal
from difflib import SequenceMatcher
from .schemas import (
    BankTransaction, Finding, Invoice, InvoiceResult, Payment, ReconciliationRequest,
    ReconciliationResponse, ToolCall,
)

ZERO = Decimal("0.00")
CENT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT)


def norm(value: str | None) -> str:
    return "".join(ch.lower() for ch in (value or "") if ch.isalnum())


def tool_search_payments(invoice: Invoice, payments: list[Payment]) -> list[Payment]:
    return [p for p in payments if p.invoice_id.casefold() == invoice.invoice_id.casefold()]


def tool_find_bank_candidates(invoice: Invoice, payments: list[Payment], bank: list[BankTransaction]) -> list[BankTransaction]:
    """Find candidates conservatively; a candidate is not automatically a confirmed match."""
    payment_refs = {norm(p.reference) for p in payments if p.reference}
    payment_ids = {norm(p.payment_id) for p in payments}
    candidates = []
    for tx in bank:
        ref = norm(tx.reference)
        desc = norm(tx.description)
        cp = norm(tx.counterparty)
        reference_hit = bool(ref and (ref in payment_refs or ref in payment_ids))
        invoice_hit = norm(invoice.invoice_id) in desc if invoice.invoice_id else False
        supplier_hit = bool(norm(invoice.supplier) and (norm(invoice.supplier) in cp or norm(invoice.supplier) in desc))
        # Bank outflows are negative. Match by reference or by supplier + aggregate invoice amount.
        amount_hit = abs(tx.amount) <= invoice.amount and abs(tx.amount) > 0
        if reference_hit or invoice_hit or (supplier_hit and amount_hit):
            candidates.append(tx)
    return candidates


def investigate(payload: ReconciliationRequest) -> ReconciliationResponse:
    trace: list[ToolCall] = []
    findings: list[Finding] = []
    invoices = payload.invoices
    payments = payload.payments
    bank = payload.bank_transactions
    invoice_ids = [i.invoice_id.casefold() for i in invoices]
    payment_ids = [p.payment_id.casefold() for p in payments]
    tx_ids = [t.transaction_id.casefold() for t in bank]

    # Verify unique record identifiers before relying on them.
    for label, ids in (("invoice", invoice_ids), ("payment", payment_ids), ("bank transaction", tx_ids)):
        seen: set[str] = set()
        duplicates = sorted({item for item in ids if item in seen or seen.add(item)})
        trace.append(ToolCall(tool="check_unique_ids", input={"record_type": label}, result=f"{len(duplicates)} duplicate identifier(s)"))
        for duplicate in duplicates:
            findings.append(Finding(
                finding_id=f"DUP-ID-{label.replace(' ', '-')}-{duplicate}", category="duplicate_record_id", severity="high",
                summary=f"Duplicate {label} identifier: {duplicate}", evidence=[f"Repeated {label} identifier {duplicate}"],
                recommendation="Review the source records; do not automatically delete or merge them."))

    # Invoice-level investigation uses tools to retrieve related records and independently verify arithmetic.
    results: list[InvoiceResult] = []
    seen_invoice_keys: set[tuple[str, str, str]] = set()
    for invoice in invoices:
        key = (norm(invoice.supplier), invoice.invoice_id.casefold(), money(invoice.amount).to_eng_string())
        if key in seen_invoice_keys:
            findings.append(Finding(
                finding_id=f"DUP-INVOICE-{invoice.invoice_id}", category="possible_duplicate_invoice", severity="high",
                summary=f"Potential duplicate invoice record {invoice.invoice_id}",
                evidence=[f"Invoice ID={invoice.invoice_id}", f"Supplier={invoice.supplier}", f"Amount={money(invoice.amount)} {invoice.currency}"],
                recommendation="Compare the original invoice document and payment history before deciding whether this is a duplicate."))
        seen_invoice_keys.add(key)

        related = tool_search_payments(invoice, payments)
        paid = money(sum((p.amount for p in related), ZERO))
        outstanding = money(invoice.amount - paid)
        trace.append(ToolCall(tool="search_payments_by_invoice", input={"invoice_id": invoice.invoice_id}, result=f"Found {len(related)} payment record(s); total={paid}"))

        candidates = tool_find_bank_candidates(invoice, related, bank)
        trace.append(ToolCall(tool="find_bank_candidates", input={"invoice_id": invoice.invoice_id}, result=f"Found {len(candidates)} possible bank transaction(s); candidates are not confirmed matches"))
        linked_bank: list[str] = []
        payment_refs = {norm(p.reference) for p in related if p.reference}
        payment_ids_for_invoice = {norm(p.payment_id) for p in related}
        for tx in candidates:
            tx_ref = norm(tx.reference)
            description = norm(tx.description)
            ref_supported = bool(tx_ref and (tx_ref in payment_refs or tx_ref in payment_ids_for_invoice))
            invoice_supported = norm(invoice.invoice_id) in description
            if ref_supported or invoice_supported:
                linked_bank.append(tx.transaction_id)

        notes: list[str] = []
        if paid == ZERO:
            status = "unpaid"
            notes.append("No internal payment records reference this invoice.")
        elif outstanding > ZERO:
            status = "partially_paid"
            notes.append(f"Outstanding balance is {outstanding} {invoice.currency}.")
        elif outstanding < ZERO:
            status = "overpaid"
            notes.append(f"Payments exceed invoice value by {abs(outstanding)} {invoice.currency}.")
        else:
            status = "paid"
            notes.append("Internal payment total equals invoice amount; bank evidence still requires matching.")

        # If the payment total is exact but no bank reference supports it, flag the evidence gap.
        if related and not linked_bank:
            status = "needs_review" if outstanding == ZERO else status
            notes.append("No bank transaction was linked by a strong reference; review possible candidates.")
            findings.append(Finding(
                finding_id=f"BANK-EVIDENCE-{invoice.invoice_id}", category="bank_match_unverified", severity="warning",
                summary=f"Bank evidence for invoice {invoice.invoice_id} is not confirmed",
                evidence=[f"Internal payments: {', '.join(p.payment_id for p in related)}", f"Candidate bank transactions: {', '.join(t.transaction_id for t in candidates) or 'none'}"],
                recommendation="Review bank references, dates, amounts, and supporting remittance details before confirming the match."))

        if status in ("partially_paid", "overpaid", "unpaid"):
            findings.append(Finding(
                finding_id=f"BALANCE-{invoice.invoice_id}", category="payment_balance", severity="warning" if status != "overpaid" else "high",
                summary=f"Invoice {invoice.invoice_id} is {status.replace('_', ' ')}",
                evidence=[f"Invoice amount: {money(invoice.amount)} {invoice.currency}", f"Recorded payments: {paid} {invoice.currency}", f"Calculated outstanding: {outstanding} {invoice.currency}"],
                recommendation="Inspect all related payment and bank records; approve any adjustment only after verification."))

        results.append(InvoiceResult(
            invoice_id=invoice.invoice_id, supplier=invoice.supplier, invoice_amount=money(invoice.amount),
            paid_amount=paid, outstanding_amount=outstanding, status=status,
            linked_payment_ids=[p.payment_id for p in related], linked_bank_transaction_ids=linked_bank, notes=notes,
        ))

    # Report unmatched bank transactions; no automatic accounting adjustment is proposed as final.
    linked_tx_ids = {txid for result in results for txid in result.linked_bank_transaction_ids}
    for tx in bank:
        if tx.transaction_id not in linked_tx_ids:
            findings.append(Finding(
                finding_id=f"UNMATCHED-BANK-{tx.transaction_id}", category="unmatched_bank_transaction", severity="warning",
                summary=f"Bank transaction {tx.transaction_id} is not strongly linked to an invoice",
                evidence=[f"Date: {tx.transaction_date}", f"Description: {tx.description}", f"Amount: {money(tx.amount)}", f"Reference: {tx.reference or 'missing'}"],
                recommendation="Search payment references and remittance evidence, or request clarification from the finance team."))

    # Basic duplicate payment detection: identical supplier/date/amount/reference signatures.
    signatures: dict[tuple[str, str, str, str], list[Payment]] = defaultdict(list)
    for p in payments:
        signatures[(norm(p.supplier), p.payment_date.isoformat(), money(p.amount).to_eng_string(), norm(p.reference))].append(p)
    for signature, records in signatures.items():
        if len(records) > 1:
            findings.append(Finding(
                finding_id=f"DUP-PAYMENT-{records[0].payment_id}", category="possible_duplicate_payment", severity="high",
                summary="Potential duplicate payment records detected",
                evidence=[f"Payment IDs: {', '.join(p.payment_id for p in records)}", f"Supplier/date/amount/reference signature: {signature}"],
                recommendation="Check bank statement transaction IDs and remittance advice before treating these as duplicate payments."))

    # Final independent verification of arithmetic from the response objects.
    arithmetic_ok = all(r.outstanding_amount == money(r.invoice_amount - r.paid_amount) for r in results)
    trace.append(ToolCall(tool="verify_balance_calculations", input={"invoice_count": len(results)}, result="PASS: all balances recomputed independently" if arithmetic_ok else "FAIL: balance mismatch"))
    if not arithmetic_ok:
        findings.append(Finding(finding_id="VERIFY-ARITHMETIC", category="verification_failure", severity="high", summary="Balance verification failed", evidence=["Recomputed balance differs from reported balance"], recommendation="Stop review and investigate calculation or data integrity issues."))

    return ReconciliationResponse(
        invoice_results=results,
        findings=findings,
        summary={
            "invoice_count": len(invoices), "payment_count": len(payments), "bank_transaction_count": len(bank),
            "fully_paid_count": sum(1 for r in results if r.status == "paid"),
            "partially_paid_count": sum(1 for r in results if r.status == "partially_paid"),
            "unpaid_count": sum(1 for r in results if r.status == "unpaid"),
            "needs_review_count": sum(1 for r in results if r.status == "needs_review"),
            "finding_count": len(findings), "verification": "passed" if arithmetic_ok else "failed",
        }, agent_trace=trace,
    )
