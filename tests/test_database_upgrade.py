import os, tempfile
from fastapi.testclient import TestClient

def test_health_and_persistent_order_apis():
    # Use a temporary SQLite file before importing the application.
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["DATABASE_URL"] = "sqlite:///" + path.replace("\\", "/")
    os.environ.pop("PAYPAL_CLIENT_ID", None)
    os.environ.pop("PAYPAL_CLIENT_SECRET", None)
    from app.main import app
    client = TestClient(app)
    h = client.get("/api/health")
    assert h.status_code == 200
    assert h.json()["database"] == "connected"
    assert h.json()["database_persistent"] is True
    assert client.get("/api/orders").status_code == 200
    assert client.get("/api/payments").status_code == 200
