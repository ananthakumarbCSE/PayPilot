import os, uuid
from pathlib import Path
from decimal import Decimal
from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc
from .agent import run_agent
from .multi_agent import orchestrate_result
from .catalog import CATALOG, get_product
from .paypal import PayPalClient, PayPalError
from .database import Base, engine, get_db
from .models import Customer, Product, Order, OrderItem, Payment, AgentEvent

Base.metadata.create_all(bind=engine)

app = FastAPI(title="PayPilot", version="2.0.0", description="Agentic commerce with persistent order and payment records")
BASE = Path(__file__).parent
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None
    history: list[dict] = Field(default_factory=list)
    preferences: dict = Field(default_factory=dict)

class CheckoutRequest(BaseModel):
    items: list[dict] = Field(min_length=1, max_length=10)
    session_id: str | None = None

class CaptureRequest(BaseModel):
    order_id: str

def get_or_create_customer(db: Session, session_id: str) -> Customer:
    customer = db.query(Customer).filter_by(session_id=session_id).first()
    if not customer:
        customer = Customer(session_id=session_id)
        db.add(customer)
        db.flush()
    return customer

def log_event(db, session_id, event_type, message, details=None):
    db.add(AgentEvent(session_id=session_id, event_type=event_type, message=message, details=details))

def serialize_order(order: Order):
    return {
        "order_id": order.public_id,
        "paypal_order_id": order.paypal_order_id,
        "status": order.status,
        "mode": order.payment_mode,
        "total": f"{Decimal(order.total):.2f}",
        "currency": order.currency,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "items": [{
            "id": item.product_id, "name": item.product_name,
            "quantity": item.quantity, "unit_price": f"{Decimal(item.unit_price):.2f}",
            "line_total": f"{Decimal(item.line_total):.2f}"
        } for item in order.items],
        "payment": ({
            "provider": order.payment.provider,
            "status": order.payment.status,
            "capture_id": order.payment.capture_id,
            "amount": f"{Decimal(order.payment.amount):.2f}",
            "currency": order.payment.currency,
        } if order.payment else None)
    }

class BudgetCompareRequest(BaseModel):
    query: str = Field(min_length=2, max_length=200)
    budget: Decimal = Field(gt=0, le=1000000)


@app.post("/api/budget/compare")
def budget_compare(req: BudgetCompareRequest):
    """Compare connected USD product results against a spending ceiling."""
    try:
        ceiling = req.budget.quantize(Decimal("0.01"))
    except Exception:
        raise HTTPException(400, "Enter a valid budget amount.")

    results = search_catalog(req.query)
    normalized = []
    for item in results:
        try:
            price = Decimal(str(item.get("price", "0"))).quantize(Decimal("0.01"))
        except Exception:
            continue
        if price <= 0 or item.get("currency", "USD") != "USD":
            continue
        row = dict(item)
        row["price"] = f"{price:.2f}"
        row["within_budget"] = price <= ceiling
        row["budget_note"] = (
            f"${ceiling - price:.2f} under budget" if price <= ceiling
            else f"${price - ceiling:.2f} over budget"
        )
        normalized.append(row)

    normalized.sort(key=lambda p: (
        not p["within_budget"],
        -(float(p.get("rating") or 0)),
        Decimal(p["price"])
    ))
    affordable = sum(1 for p in normalized if p["within_budget"])
    return {
        "query": req.query,
        "budget": f"{ceiling:.2f}",
        "currency": "USD",
        "matched_count": len(normalized),
        "affordable_count": affordable,
        "products": normalized[:12],
        "message": (
            f"{affordable} of {len(normalized)} returned options are within your ${ceiling:.2f} budget."
            if normalized else "No comparable USD product options were found for this search."
        )
    }


@app.get("/", response_class=HTMLResponse)
def home():
    return (BASE / "static" / "index.html").read_text(encoding="utf-8")

@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    pp = PayPalClient()
    return {
        "status": "ok", "paypal_configured": pp.configured,
        "ai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "payment_mode": "paypal-sandbox" if pp.configured else "simulation",
        "database": "connected", "database_type": engine.dialect.name,
        "database_persistent": True
    }

@app.get("/api/catalog")
def catalog():
    return {"products": CATALOG}

@app.post("/api/agent/chat")
def chat(req: ChatRequest, db: Session = Depends(get_db)):
    result = run_agent(req.message, req.history)
    result = orchestrate_result(result, req.message, req.preferences)
    session_id = req.session_id or str(uuid.uuid4())
    get_or_create_customer(db, session_id)
    log_event(db, session_id, "CHAT", req.message[:500], {"has_cart": bool(result.get("cart"))})
    db.commit()
    return {**result, "session_id": session_id}

def validate_cart(items):
    clean, cents = [], 0
    for row in items:
        product = get_product(str(row.get("id") or row.get("product_id") or ""))
        if not product:
            raise HTTPException(400, "Cart contains an unknown product.")
        qty = int(row.get("quantity", 1))
        if qty < 1 or qty > 5:
            raise HTTPException(400, "Quantity must be between 1 and 5.")
        unit = int(round(float(product["price"]) * 100))
        line = unit * qty
        cents += line
        clean.append({"id": product["id"], "name": product["name"], "quantity": qty,
                      "unit_price": f"{unit/100:.2f}", "line_total": f"{line/100:.2f}"})
    return clean, f"{cents/100:.2f}"


class PrepareCartRequest(BaseModel):
    items: list[dict] = Field(min_length=1, max_length=10)


@app.post("/api/cart/prepare")
def prepare_cart_endpoint(req: PrepareCartRequest):
    clean, total = validate_cart(req.items)
    enriched = []
    for item in clean:
        product = get_product(item["id"])
        enriched.append({
            **item,
            "description": product.get("description", "") if product else "",
            "image": product.get("image") if product else None,
            "source": product.get("source") if product else None,
        })
    return {"items": enriched, "total": total, "currency": "USD"}

@app.post("/api/paypal/create-order")
def create_order(req: CheckoutRequest, request: Request, db: Session = Depends(get_db)):
    clean, total = validate_cart(req.items)
    session_id = req.session_id or str(uuid.uuid4())
    customer = get_or_create_customer(db, session_id)
    pp = PayPalClient()
    if pp.configured:
        try:
            base_url = str(request.base_url).rstrip("/")
            data = pp.create_order(
    clean,
    total,
    f"{base_url}/api/paypal/return",
    f"{base_url}/api/paypal/cancel"
)
        except PayPalError as e:
            db.rollback()
            raise HTTPException(502, str(e))
        paypal_order_id = data["id"]
        approve = next((x["href"] for x in data.get("links", []) if x.get("rel") in ("payer-action", "approve")), None)
        if not approve:
            raise HTTPException(502, "PayPal created the order but did not return a buyer approval link.")
        mode = "paypal-sandbox"
        public_id = "PP-" + uuid.uuid4().hex[:12].upper()
    else:
        paypal_order_id = None
        approve = None
        mode = "simulation"
        public_id = "DEMO-" + uuid.uuid4().hex[:12].upper()

    order = Order(public_id=public_id, customer_id=customer.id, paypal_order_id=paypal_order_id,
                  status="PENDING_APPROVAL" if pp.configured else "CREATED",
                  payment_mode=mode, currency="USD", total=Decimal(total))
    db.add(order)
    db.flush()
    for item in clean:
        db.add(OrderItem(order_id=order.id, product_id=item["id"], product_name=item["name"],
                         quantity=item["quantity"], unit_price=Decimal(item["unit_price"]),
                         line_total=Decimal(item["line_total"])))
    if pp.configured:
        db.add(Payment(order_id=order.id, provider="paypal", provider_order_id=paypal_order_id,
                       status="PENDING_APPROVAL", amount=Decimal(total), currency="USD"))
    log_event(db, session_id, "ORDER_CREATED", "Order created and stored", {"order_id": public_id, "paypal_order_id": paypal_order_id})
    db.commit()
    return {"order_id": public_id, "paypal_order_id": paypal_order_id, "approve_url": approve,
            "total": total, "currency": "USD", "mode": mode}

def complete_payment_for_order(order, db):
    """Verify PayPal approval and capture the payment server-side."""

    if order.status == "COMPLETED":
        return {"status": "COMPLETED", **serialize_order(order)}

    if order.payment_mode != "paypal-sandbox":
        order.status = "COMPLETED"
        if order.payment:
            order.payment.status = "COMPLETED"
        db.commit()
        db.refresh(order)
        return {"status": "COMPLETED", **serialize_order(order)}

    client = PayPalClient()

    try:
        paypal_order = client.get_order(order.paypal_order_id)
        paypal_status = paypal_order.get("status", "UNKNOWN")

        # Reconcile a payment if PayPal already captured it.
        if paypal_status == "COMPLETED":
            data = paypal_order

        elif paypal_status == "APPROVED":
            data = client.capture_order(order.paypal_order_id)

        else:
            raise HTTPException(
                status_code=409,
                detail=f"PayPal order is {paypal_status}; buyer approval is required."
            )

    except PayPalError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    if data.get("status") != "COMPLETED":
        raise HTTPException(
            status_code=409,
            detail=f"PayPal reports order status: {data.get('status', 'UNKNOWN')}"
        )

    captures = []

    for unit in data.get("purchase_units", []):
        for capture_row in unit.get("payments", {}).get("captures", []):
            captures.append(capture_row)

    capture_id = captures[0].get("id") if captures else None

    if not capture_id:
        raise HTTPException(
            status_code=502,
            detail="PayPal reports COMPLETED but returned no capture ID."
        )

    if order.payment:
        order.payment.status = "COMPLETED"
        order.payment.capture_id = capture_id
        order.payment.raw_response = data

    order.status = "COMPLETED"

    order.updated_at = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    )

    log_event(
        db,
        str(order.customer.session_id),
        "PAYMENT_COMPLETED",
        "PayPal payment captured and reconciled",
        {
            "order_id": order.public_id,
            "capture_id": capture_id
        }
    )

    db.commit()
    db.refresh(order)

    return {"status": "COMPLETED", **serialize_order(order)}


@app.get("/api/paypal/return")
def paypal_return(token: str, db: Session = Depends(get_db)):
    from urllib.parse import quote

    order = db.query(Order).options(
        joinedload(Order.items),
        joinedload(Order.payment),
        joinedload(Order.customer)
    ).filter_by(paypal_order_id=token).first()

    if not order:
        return RedirectResponse(
            url="/?payment=error&message=Order%20not%20found",
            status_code=303
        )

    try:
        complete_payment_for_order(order, db)

        return RedirectResponse(
            url=f"/?payment=success&order_id={quote(order.public_id)}",
            status_code=303
        )

    except HTTPException as exc:
        return RedirectResponse(
            url=f"/?payment=error&message={quote(str(exc.detail))}",
            status_code=303
        )


@app.get("/api/paypal/cancel")
def paypal_cancel(token: str | None = None, db: Session = Depends(get_db)):
    """Record a buyer-returned PayPal cancellation without capturing funds."""
    from urllib.parse import quote

    if token:
        order = db.query(Order).options(
            joinedload(Order.payment),
            joinedload(Order.customer)
        ).filter_by(paypal_order_id=token).first()

        if order and order.status not in ("COMPLETED", "CANCELLED"):
            order.status = "CANCELLED"
            if order.payment and order.payment.status != "COMPLETED":
                order.payment.status = "CANCELLED"
            log_event(
                db,
                str(order.customer.session_id),
                "CHECKOUT_CANCELLED",
                "Buyer returned from PayPal without approving payment",
                {"order_id": order.public_id}
            )
            db.commit()

    return RedirectResponse(url="/?payment=cancel", status_code=303)



@app.post("/api/paypal/capture")
def capture(req: CaptureRequest, db: Session = Depends(get_db)):

    order = db.query(Order).options(
        joinedload(Order.items),
        joinedload(Order.payment),
        joinedload(Order.customer)
    ).filter_by(public_id=req.order_id).first()

    if not order:
        order = db.query(Order).options(
            joinedload(Order.items),
            joinedload(Order.payment),
            joinedload(Order.customer)
        ).filter_by(paypal_order_id=req.order_id).first()

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found. Start a fresh checkout."
        )

    return complete_payment_for_order(order, db)


@app.get("/api/orders")
def orders(limit: int = 50, db: Session = Depends(get_db)):
    rows = db.query(Order).options(joinedload(Order.items), joinedload(Order.payment)).order_by(desc(Order.created_at)).limit(min(max(limit,1),200)).all()
    return {"orders": [serialize_order(row) for row in rows]}

@app.get("/api/orders/{order_id}")
def order_detail(order_id: str, db: Session = Depends(get_db)):
    row = db.query(Order).options(joinedload(Order.items), joinedload(Order.payment)).filter_by(public_id=order_id).first()
    if not row:
        raise HTTPException(404, "Order not found.")
    return serialize_order(row)

@app.get("/api/payments")
def payments(limit: int = 50, db: Session = Depends(get_db)):
    rows = db.query(Payment).join(Order).order_by(desc(Payment.created_at)).limit(min(max(limit,1),200)).all()
    return {"payments": [{
        "order_id": row.order.public_id, "paypal_order_id": row.provider_order_id,
        "capture_id": row.capture_id, "status": row.status,
        "amount": f"{Decimal(row.amount):.2f}", "currency": row.currency,
        "created_at": row.created_at.isoformat() if row.created_at else None
    } for row in rows]}

@app.get("/api/agent/events")
def agent_events(limit: int = 100, db: Session = Depends(get_db)):
    rows = db.query(AgentEvent).order_by(desc(AgentEvent.created_at)).limit(min(max(limit,1),500)).all()
    return {"events": [{
        "id": row.id, "session_id": row.session_id, "event_type": row.event_type,
        "message": row.message, "details": row.details,
        "created_at": row.created_at.isoformat() if row.created_at else None
    } for row in rows]}


@app.get("/api/analytics/overview")
def analytics_overview(days: int = 14, db: Session = Depends(get_db)):
    """Database-backed commerce KPIs and chart series for the operations dashboard."""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import func

    days = min(max(days, 7), 90)
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days - 1)
    orders_q = db.query(Order)
    orders = orders_q.all()
    payments = db.query(Payment).all()

    total_orders = len(orders)
    completed_orders = sum(1 for row in orders if row.status == "COMPLETED")
    pending_orders = sum(1 for row in orders if row.status in ("PENDING_APPROVAL", "CREATED", "PENDING"))
    failed_orders = sum(1 for row in orders if row.status in ("FAILED", "CANCELLED"))
    captured_revenue = sum(
        (Decimal(str(p.amount)) for p in payments if p.status == "COMPLETED"),
        Decimal("0.00")
    )
    payment_count = len(payments)
    completed_payments = sum(1 for p in payments if p.status == "COMPLETED")
    success_rate = round((completed_payments / payment_count) * 100, 1) if payment_count else 0

    # Build a complete date range so zero-activity days still render in charts.
    daily = {}
    for offset in range(days):
        day = (start + timedelta(days=offset)).date().isoformat()
        daily[day] = {"date": day, "orders": 0, "revenue": 0.0}
    for order in orders:
        created = order.created_at
        if created:
            day = created.date().isoformat()
            if day in daily:
                daily[day]["orders"] += 1
    for payment in payments:
        created = payment.updated_at or payment.created_at
        if payment.status == "COMPLETED" and created:
            day = created.date().isoformat()
            if day in daily:
                daily[day]["revenue"] += float(payment.amount)

    status_counts = {}
    for order in orders:
        status_counts[order.status] = status_counts.get(order.status, 0) + 1

    product_totals = {}
    for order in orders:
        if order.status != "COMPLETED":
            continue
        for item in order.items:
            key = item.product_name
            product_totals[key] = product_totals.get(key, 0) + int(item.quantity)
    top_products = [
        {"name": name, "units": qty}
        for name, qty in sorted(product_totals.items(), key=lambda item: item[1], reverse=True)[:6]
    ]

    event_count = db.query(AgentEvent).count()
    chat_count = db.query(AgentEvent).filter(AgentEvent.event_type == "CHAT").count()
    order_created_events = db.query(AgentEvent).filter(AgentEvent.event_type == "ORDER_CREATED").count()

    return {
        "generated_at": now.isoformat(),
        "period_days": days,
        "kpis": {
            "total_orders": total_orders,
            "completed_orders": completed_orders,
            "pending_orders": pending_orders,
            "failed_or_cancelled_orders": failed_orders,
            "captured_revenue": f"{captured_revenue:.2f}",
            "payment_count": payment_count,
            "completed_payments": completed_payments,
            "payment_success_rate": success_rate,
        },
        "daily": list(daily.values()),
        "order_statuses": [{"status": key, "count": value} for key, value in sorted(status_counts.items())],
        "top_products": top_products,
        "activity": {
            "total_events": event_count,
            "chat_requests": chat_count,
            "orders_created": order_created_events,
            "completed_payments": completed_payments,
        },
    }


@app.get("/api/analytics/recent-activity")
def analytics_recent_activity(limit: int = 12, db: Session = Depends(get_db)):
    limit = min(max(limit, 1), 50)
    rows = db.query(AgentEvent).order_by(desc(AgentEvent.created_at)).limit(limit).all()
    return {"events": [{
        "id": row.id,
        "type": row.event_type,
        "message": row.message,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "details": row.details or {},
    } for row in rows]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=False)

@app.get("/admin", response_class=HTMLResponse)
def admin():
    return (BASE / "static" / "database.html").read_text(encoding="utf-8")
