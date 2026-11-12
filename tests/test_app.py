from fastapi.testclient import TestClient
from app.main import app, ORDERS

client = TestClient(app)

def test_health_and_catalog():
    h = client.get("/api/health")
    assert h.status_code == 200 and h.json()["status"] == "ok"
    products = client.get("/api/catalog").json()["products"]
    assert len(products) >= 5

def test_agent_returns_guided_response_without_keys(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = client.post("/api/agent/chat", json={"message": "I need a desk lamp"})
    assert r.status_code == 200
    assert "lamp" in r.json()["reply"].lower()
    assert r.json()["session_id"]

def test_create_and_capture_demo_order(monkeypatch):
    monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET", raising=False)
    r = client.post("/api/paypal/create-order", json={"items": [{"id": "desk-lamp", "quantity": 2}]})
    assert r.status_code == 200
    data = r.json()
    assert data["mode"] == "simulation"
    assert data["total"] == "78.00"
    c = client.post("/api/paypal/capture", json={"order_id": data["order_id"]})
    assert c.status_code == 200
    assert c.json()["status"] == "COMPLETED"
    assert c.json()["mode"] == "simulation"

def test_server_rejects_client_price_manipulation(monkeypatch):
    monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET", raising=False)
    r = client.post("/api/paypal/create-order", json={"items": [{"id": "desk-lamp", "quantity": 1, "unit_price": "0.01"}]})
    assert r.status_code == 200
    assert r.json()["total"] == "39.00"

def test_unknown_product_rejected():
    r = client.post("/api/paypal/create-order", json={"items": [{"id": "made-up", "quantity": 1}]})
    assert r.status_code == 400

def test_quantity_limits():
    r = client.post("/api/paypal/create-order", json={"items": [{"id": "desk-lamp", "quantity": 99}]})
    assert r.status_code == 400


def test_agent_prepare_cart_returns_server_computed_proposal(monkeypatch):
    from app.agent import _prepare_cart
    cart = _prepare_cart({"items": [{"product_id": "desk-lamp", "quantity": 2}]})
    assert cart["total"] == "78.00"
    assert cart["items"][0]["id"] == "desk-lamp"
    assert cart["items"][0]["line_total"] == "78.00"


def test_paypal_order_payload_contains_required_item_total(monkeypatch):
    from app.paypal import PayPalClient
    import app.paypal as paypal_module
    client = PayPalClient()
    client.client_id = "sandbox-client"
    client.secret = "sandbox-secret"
    calls = []
    class Response:
        ok = True
        def __init__(self, payload): self.payload = payload
        def json(self): return self.payload
    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("/v1/oauth2/token"):
            return Response({"access_token": "token"})
        return Response({"id": "ORDER-123", "links": [{"rel": "payer-action", "href": "https://sandbox.example/approve"}]})
    monkeypatch.setattr(paypal_module.requests, "post", fake_post)
    data = client.create_order([{"name":"Lamp","quantity":2,"unit_price":"39.00"}],
                               "78.00","https://demo.example/return","https://demo.example/cancel")
    payload = calls[1][1]["json"]
    assert payload["purchase_units"][0]["amount"]["breakdown"]["item_total"]["value"] == "78.00"
    assert data["id"] == "ORDER-123"
