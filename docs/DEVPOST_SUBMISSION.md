# Devpost Submission Draft

## Project name
PayPilot — Agentic Commerce

## One-line description
An AI shopping agent that turns natural-language intent into a validated PayPal checkout, with the customer in control of every payment.

## Inspiration
People often know the outcome they want, not the exact product filters and checkout steps required to get there. Small merchants also need better ways to turn customer conversations into completed orders. We built PayPilot to bridge that gap.

## What it does
PayPilot interprets natural-language shopping requests, searches a merchant catalog, prepares a transparent itemized order, validates prices server-side, and creates a PayPal Sandbox order. The customer approves on PayPal before the backend captures and verifies the transaction.

## How we built it
FastAPI orchestrates a bounded LLM tool-calling agent. The model can search the catalog and prepare a cart proposal. It cannot directly charge a customer. The server independently validates product IDs, quantities, and prices before calling PayPal Orders v2. The frontend presents the proposal and sends the customer to PayPal for approval.

## What makes it different
The project treats checkout as an agentic workflow, not a chatbot wrapper around a payment button. The AI is useful before checkout—interpreting intent, searching, recommending, and assembling an order—while payment authority remains in a deterministic backend and PayPal approval flow.

## Built with
PayPal REST API (Sandbox Orders v2), Python, FastAPI, OpenAI-compatible tool calling, HTML, CSS, JavaScript, Pytest.

## Responsible AI and payments
The model has bounded tools and no direct payment authority. Prices are sourced from the server catalog. Order creation is distinct from capture. PayPal approval is performed by the buyer. The backend reports a completed Sandbox payment only after PayPal returns a completed capture status.

## Links to add before submission
- Public source repository: [ADD URL]
- Hosted demo: [ADD URL or repository run instructions]
- YouTube demo (under 3 minutes): [ADD URL]
