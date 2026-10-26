from datetime import date
from decimal import Decimal
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .schemas import ReconciliationRequest, ReconciliationResponse
from .agent import investigate

app = FastAPI(
    title="AI Agent for Intelligent Invoice and Payment Reconciliation",
    description="A synthetic-data prototype that matches financial records, investigates exceptions using tools, verifies balances, and recommends human-reviewed next steps.",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["*"],
)

@app.get("/", tags=["System"])
def root():
    return {"project": app.title, "status": "starter-running", "docs": "/docs", "safety": "Synthetic data only; recommendations require human review."}

@app.get("/health", tags=["System"])
def health():
    return {"status": "ok"}

@app.get("/demo-data", response_model=ReconciliationRequest, tags=["Demo"])
def demo_data():
    """Return intentionally mixed synthetic records for a first live demo."""
    return ReconciliationRequest(
        invoices=[
            {"invoice_id":"INV-1001","supplier":"Apex Supplies","invoice_date":date(2026,10,1),"due_date":date(2026,10,31),"amount":Decimal("50000.00"),"currency":"INR"},
            {"invoice_id":"INV-1002","supplier":"Bright Office","invoice_date":date(2026,10,3),"due_date":date(2026,10,25),"amount":Decimal("18000.00"),"currency":"INR"},
            {"invoice_id":"INV-1003","supplier":"Apex Supplies","invoice_date":date(2026,10,5),"due_date":date(2026,11,5),"amount":Decimal("12000.00"),"currency":"INR"},
            {"invoice_id":"INV-1003","supplier":"Apex Supplies","invoice_date":date(2026,10,5),"due_date":date(2026,11,5),"amount":Decimal("12000.00"),"currency":"INR"},
        ],
        payments=[
            {"payment_id":"PAY-501","invoice_id":"INV-1001","supplier":"Apex Supplies","payment_date":date(2026,10,10),"amount":Decimal("30000.00"),"reference":"NEFT-AX501"},
            {"payment_id":"PAY-502","invoice_id":"INV-1001","supplier":"Apex Supplies","payment_date":date(2026,10,12),"amount":Decimal("20000.00"),"reference":"NEFT-AX502"},
            {"payment_id":"PAY-503","invoice_id":"INV-1002","supplier":"Bright Office","payment_date":date(2026,10,14),"amount":Decimal("15000.00"),"reference":"BO-503"},
            {"payment_id":"PAY-504","invoice_id":"INV-1003","supplier":"Apex Supplies","payment_date":date(2026,10,15),"amount":Decimal("12000.00"),"reference":"AX-504"},
        ],
        bank_transactions=[
            {"transaction_id":"BNK-901","transaction_date":date(2026,10,10),"description":"NEFT Apex Supplies INV-1001","counterparty":"Apex Supplies","amount":Decimal("-30000.00"),"reference":"NEFT-AX501"},
            {"transaction_id":"BNK-902","transaction_date":date(2026,10,12),"description":"NEFT Apex Supplies INV-1001","counterparty":"Apex Supplies","amount":Decimal("-20000.00"),"reference":"NEFT-AX502"},
            {"transaction_id":"BNK-903","transaction_date":date(2026,10,14),"description":"Transfer Bright Office","counterparty":"Bright Office","amount":Decimal("-15000.00"),"reference":"UNKNOWN-903"},
            {"transaction_id":"BNK-904","transaction_date":date(2026,10,16),"description":"Unidentified vendor transfer","counterparty":"Unknown Vendor","amount":Decimal("-7250.00"),"reference":None},
        ],
    )

@app.post("/reconcile", response_model=ReconciliationResponse, tags=["Reconciliation"])
def reconcile(payload: ReconciliationRequest):
    """Run deterministic reconciliation and a transparent tool-using investigation pass."""
    return investigate(payload)
