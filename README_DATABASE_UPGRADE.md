# PayPilot Database Upgrade (v2)

This upgrade adds persistent SQL storage, order/payment history APIs, and a small operations dashboard.

## Local setup (Windows PowerShell)

1. Stop the old server with `Ctrl+C`.
2. Back up your current project folder.
3. Copy the contents of this ZIP over your existing `PayPilot` folder (allow replacements).
4. Activate your virtual environment:
   ```powershell
   .venv\Scripts\activate
   ```
5. Install the new dependencies:
   ```powershell
   python -m pip install --no-cache-dir --index-url https://pypi.org/simple -r requirements.txt
   ```
6. Copy `.env.example` to `.env` only if you do not already have `.env`. Preserve your existing PayPal and OpenAI credentials.
7. Start the app:
   ```powershell
   python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

By default the app creates `data/paypilot.db` (SQLite) automatically. It is a persistent relational database file and survives restarts. Do not delete the `data` folder.

## Database dashboard and APIs

- Operations dashboard: http://127.0.0.1:8000/admin
- Health: http://127.0.0.1:8000/api/health
- Orders: http://127.0.0.1:8000/api/orders
- Payments: http://127.0.0.1:8000/api/payments
- Agent audit events: http://127.0.0.1:8000/api/agent/events
- OpenAPI docs: http://127.0.0.1:8000/docs

## PostgreSQL for deployment

The same SQLAlchemy models support PostgreSQL. Create a database named `paypilot`, then set:
`DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/paypilot`

Keep credentials in environment variables; never commit `.env`. For production, use database migrations (Alembic), managed backups, HTTPS, authentication/authorization for `/admin`, and verified PayPal webhooks before treating this as production-ready.

## Important payment behavior

- A local order is stored before the buyer is redirected to PayPal.
- PayPal order IDs are stored in the `orders` and `payments` tables.
- A successful capture stores the PayPal capture ID and raw response.
- Capture is only attempted after the server checks PayPal order status is `APPROVED`.
- The local simulation mode is clearly marked and is not a real PayPal transaction.
- If PayPal approval/capture fails, the order remains in the database for troubleshooting.

The app does not store card numbers, CVVs, PayPal passwords, or API secrets in the database.

## Optional: run PostgreSQL locally with Docker

If Docker Desktop is installed and running:

```powershell
docker compose up -d
```

Then change `DATABASE_URL` in `.env` to:

```env
DATABASE_URL=postgresql+psycopg://paypilot:change-this-local-password@localhost:5432/paypilot
```

Restart PayPilot. SQLAlchemy will create the tables automatically on first startup. The named Docker volume keeps the PostgreSQL data when the container is restarted. Change the example password for any shared environment.
