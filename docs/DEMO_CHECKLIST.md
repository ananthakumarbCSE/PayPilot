# Demo readiness checklist

- [ ] `python -m venv .venv`
- [ ] Install `requirements.txt`
- [ ] Copy `.env.example` to `.env`
- [ ] Set PayPal Sandbox app Client ID and Secret
- [ ] Set OpenAI API key
- [ ] Start server with `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- [ ] Confirm `/api/health` says `paypal_configured: true` and `ai_configured: true`
- [ ] Use a Sandbox buyer account to approve a test payment
- [ ] Capture and show PayPal `COMPLETED`
- [ ] Run `pytest -q`
- [ ] Record a clean 2:30 max demo; do not include secrets or copyrighted music
