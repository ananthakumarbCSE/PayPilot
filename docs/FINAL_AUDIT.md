# Final submission audit checklist

## App smoke tests
- [ ] `/api/health` reports database connected.
- [ ] OpenAI configuration status is understood; if FALLBACK appears, do not describe that specific run as live OpenAI reasoning.
- [ ] Product search returns relevant results or a clear no-match response.
- [ ] Product source labels distinguish curated demo, DummyJSON sample data, and optional external listings.
- [ ] Explainable recommendation reasons are grounded in returned product fields.
- [ ] Budget comparison works and correctly marks under/over-budget USD items.
- [ ] Agent trace shows Shopping, Budget, Trust, Personalization and Supervisor statuses.
- [ ] Preference save, reload persistence, and Clear all work.
- [ ] Eligible product can be added to proposal; external marketplace item cannot.
- [ ] PayPal Sandbox buyer approval succeeds.
- [ ] PayPal Sandbox cancellation records CANCELLED and does not capture funds.
- [ ] Order and payment appear in Operations & analytics.

## GitHub / repository
- [ ] Repository visibility is Public.
- [ ] `README.md` contains complete setup and run instructions.
- [ ] `LICENSE` is present.
- [ ] `.gitignore` excludes `.env`, `.venv`, databases and local data.
- [ ] `.env.example` contains placeholders only.
- [ ] No `.env`, credentials, tokens, database, or private customer data are committed.
- [ ] All source files needed to run the app are committed.

## Devpost
- [ ] Project description explains the problem, solution, architecture, AI role, PayPal integration, safety and limitations.
- [ ] Tools field names OpenAI, PayPal Orders API Sandbox, FastAPI, SQLAlchemy, SQLite, DummyJSON, and optional eBay integration accurately.
- [ ] Public GitHub repository URL is added.
- [ ] Public demo video URL is added and video is under 3 minutes.
- [ ] Hosted URL OR complete setup instructions are provided.
- [ ] Final submission is saved before the displayed deadline.

## Accuracy guardrails
- [ ] Do not call DummyJSON data live inventory.
- [ ] Do not call Sandbox transactions real payments.
- [ ] Do not claim optional eBay is active unless configured and tested.
- [ ] Do not claim five separate LLM agents; describe hybrid specialist orchestration.
- [ ] Do not claim a hosted deployment unless it is actually online and tested.
