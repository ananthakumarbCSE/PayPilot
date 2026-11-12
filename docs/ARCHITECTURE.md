# Architecture and threat boundaries

## Request lifecycle

1. Browser sends a customer message to `/api/agent/chat`.
2. LLM receives bounded function tools: `search_catalog` and `prepare_cart`.
3. Tool implementations execute locally; catalog records and prices are server-owned.
4. Cart proposal is returned to the browser for review.
5. Browser sends product IDs and quantities to `/api/paypal/create-order`.
6. Server rehydrates products from catalog and computes total in integer cents.
7. PayPal adapter obtains OAuth token and creates Orders v2 order.
8. Customer approves at PayPal.
9. Browser requests `/api/paypal/capture`; server captures via Orders v2 and verifies `COMPLETED`.

## Trust boundaries

- LLM output is untrusted. It may suggest product IDs, but server validates all IDs and quantities.
- Browser payload is untrusted. Submitted prices are ignored.
- PayPal credentials are server-side environment variables only.
- The AI cannot invoke the payment adapter.
- A simulation order is labelled as simulation and is never described as a PayPal transaction.

## Production hardening backlog

- Persist sessions/orders in PostgreSQL.
- Add authenticated merchant and buyer identities.
- Add idempotency keys for create/capture and webhook reconciliation.
- Verify PayPal webhook signatures.
- Add rate limits, CSRF protections, secure cookies, and strict CORS.
- Add structured audit trail and policy evaluation for refunds/returns.
- Add inventory reservation and fulfillment state machine.
- Use secrets manager and rotate credentials.
