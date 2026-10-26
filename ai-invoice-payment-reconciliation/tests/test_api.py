from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_demo_data_and_reconcile():
    demo = client.get("/demo-data")
    assert demo.status_code == 200
    response = client.post("/reconcile", json=demo.json())
    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["invoice_count"] == 4
    assert data["summary"]["verification"] == "passed"
    assert len(data["agent_trace"]) > 0
    assert any(f["category"] == "possible_duplicate_invoice" for f in data["findings"])
    assert any(f["category"] == "unmatched_bank_transaction" for f in data["findings"])

def test_partial_payment_balance():
    payload = {
      "invoices": [{"invoice_id":"I-1","supplier":"Supplier A","invoice_date":"2026-10-01","amount":"100.00","currency":"INR"}],
      "payments": [{"payment_id":"P-1","invoice_id":"I-1","supplier":"Supplier A","payment_date":"2026-10-02","amount":"40.00","reference":"R-1"}],
      "bank_transactions": []
    }
    response = client.post("/reconcile", json=payload)
    assert response.status_code == 200
    result = response.json()["invoice_results"][0]
    assert result["status"] == "partially_paid"
    assert result["paid_amount"] == "40.00"
    assert result["outstanding_amount"] == "60.00"

def test_invalid_negative_invoice_amount_rejected():
    payload = {"invoices":[{"invoice_id":"I-1","supplier":"S","invoice_date":"2026-10-01","amount":"-10.00"}],"payments":[],"bank_transactions":[]}
    response = client.post("/reconcile", json=payload)
    assert response.status_code == 422
