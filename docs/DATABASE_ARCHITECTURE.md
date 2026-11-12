# PayPilot persistent data architecture

SQLAlchemy models:
- customers: anonymous browser session identity (not a full authentication system)
- products: product schema reserved for persisted catalogue synchronization
- orders: local order identity, PayPal order ID, status, total and currency
- order_items: immutable price/name snapshots at order time
- payments: provider order ID, capture ID, status, amount, currency and raw provider response
- agent_events: basic audit trail for chat/order/payment lifecycle events

Local default is SQLite (`data/paypilot.db`) to make Windows setup frictionless. Configure `DATABASE_URL` to use PostgreSQL in deployment. The same ORM models and API routes are used for both.
