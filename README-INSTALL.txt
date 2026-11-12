# PayPilot Multi-Source Product Discovery Upgrade

## What this upgrade adds
- Search across the existing curated PayPilot catalog.
- Search DummyJSON's public sample product API for a much wider demo catalog (laptops, phones, electronics, accessories, etc.).
- Optional eBay Browse API keyword search when eBay application credentials are configured.
- Product cards with images, source labels, prices and relevant action links.
- A relevance-safe fallback: if no relevant product is found, PayPilot says so instead of recommending an unrelated lamp.
- Budget filtering for common phrases such as "under $800".
- Checkout guardrails: PayPilot/DummyJSON demo items can be proposed in PayPal Sandbox; eBay listings are view-only and link to the seller. PayPilot does not pretend to purchase from eBay.
- Existing PayPal flow, SQLite persistence, analytics API and analytics dashboard retained.

## Important product-source distinction
1. **PayPilot curated catalog**: small set of products maintained by the project.
2. **DummyJSON**: external sample/mock product data. Its prices and availability are not real retailer inventory. These products are suitable for a hackathon demo; PayPal Sandbox checkout is a demo transaction to the PayPilot Sandbox merchant, not a purchase from DummyJSON.
3. **eBay Browse API**: optional marketplace listing discovery. The customer opens the actual eBay listing to transact with its seller. eBay items are deliberately not eligible for PayPilot's own PayPal checkout.

## Install on Windows / PowerShell
1. Stop Uvicorn with `Ctrl + C`.
2. Back up your current PayPilot project folder.
3. Extract this ZIP.
4. Copy the included files into the existing project, keeping the same paths:
   - `app/agent.py` -> `PayPilot/app/agent.py`
   - `app/catalog.py` -> `PayPilot/app/catalog.py`
   - `app/main.py` -> `PayPilot/app/main.py`
   - `app/models.py` -> `PayPilot/app/models.py`
   - `app/static/index.html` -> `PayPilot/app/static/index.html`
   - `app/static/database.html` -> `PayPilot/app/static/database.html`
   - `requirements.txt` -> `PayPilot/requirements.txt`
5. Do **not** replace `.env`, `app/database.py`, `app/paypal.py`, or `data/paypilot.db`.
6. Activate your existing virtual environment and start the app:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```
7. Open:
   - Shopping app: http://127.0.0.1:8000
   - Operations analytics: http://127.0.0.1:8000/admin
   - Product search API: http://127.0.0.1:8000/api/catalog/search?q=laptop
   - Analytics API: http://127.0.0.1:8000/api/analytics/overview?days=14

## Optional eBay connector setup
The DummyJSON connector works without credentials. To enable eBay Browse API, create an application in the eBay Developers Program and add these keys to your existing `.env` file (never paste secrets into chat):

```dotenv
EBAY_CLIENT_ID=your_ebay_application_client_id
EBAY_CLIENT_SECRET=your_ebay_application_client_secret
EBAY_ENV=production
EBAY_MARKETPLACE_ID=EBAY_US
```

Use `EBAY_ENV=sandbox` only if your eBay developer account supports the Browse API sandbox endpoint. eBay Browse API uses an application access token via OAuth client credentials. Access and production use may be subject to eBay developer program requirements/approval.

Restart Uvicorn after changing `.env`. If no eBay credentials are set, PayPilot simply omits eBay results.

## Test after installation
1. Search for `laptop` or `I want to buy a laptop`.
2. Confirm the recommendations are laptop-related, not desk lamps.
3. Try `wireless headphones`, `smartphone`, `sneakers`, `skincare` and `camera`.
4. Try `laptop under $800`; products above the requested maximum should be filtered out.
5. If eBay is configured, verify eBay results show **View seller listing** rather than **Ask agent to add**.
6. Test a PayPilot/DummyJSON demo product checkout with a Sandbox buyer account.

## Technical notes
- DummyJSON product IDs are cached in application memory after search so the existing server-side cart validation can validate the selected demo product. Restarting the server clears this short-lived cache; search again before preparing a new cart.
- eBay listings are not cached as PayPilot checkout products and cannot enter the PayPilot cart.
- Analytics continue to use the existing SQL database; no schema migration is required.
- External API timeouts/failures fail safely. No unrelated catalog item is substituted.
