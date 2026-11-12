"""PayPal REST Orders v2 integration. Sandbox is the default and only supported mode."""
import os
import requests

class PayPalError(RuntimeError):
    pass

class PayPalClient:
    def __init__(self):
        self.client_id = os.getenv("PAYPAL_CLIENT_ID", "").strip()
        self.secret = os.getenv("PAYPAL_CLIENT_SECRET", "").strip()
        self.base = "https://api-m.sandbox.paypal.com"

    @property
    def configured(self):
        return bool(self.client_id and self.secret)

    def _token(self):
        if not self.configured:
            raise PayPalError("PayPal Sandbox credentials are not configured.")
        r = requests.post(
            f"{self.base}/v1/oauth2/token",
            auth=(self.client_id, self.secret),
            headers={"Accept": "application/json", "Accept-Language": "en_US"},
            data={"grant_type": "client_credentials"},
            timeout=20,
        )
        if not r.ok:
            raise PayPalError(f"PayPal authentication failed ({r.status_code}): {r.text[:300]}")
        return r.json()["access_token"]

    def create_order(self, items, total, return_url, cancel_url):
        token = self._token()
        payload = {
            "intent": "CAPTURE",
            "purchase_units": [{
                "reference_id": "PAYPILOT-DEMO",
                "description": "PayPilot AI-assisted checkout",
                "amount": {"currency_code": "USD", "value": total, "breakdown": {"item_total": {"currency_code": "USD", "value": total}}},
                "items": [{
                    "name": item["name"][:127],
                    "quantity": str(item["quantity"]),
                    "unit_amount": {"currency_code": "USD", "value": item["unit_price"]},
                    "category": "PHYSICAL_GOODS",
                } for item in items],
            }],
            "payment_source": {"paypal": {"experience_context": {
                "payment_method_preference": "IMMEDIATE_PAYMENT_REQUIRED",
                "brand_name": "PayPilot Demo Store",
                "landing_page": "LOGIN",
                "user_action": "PAY_NOW",
                "return_url": return_url,
                "cancel_url": cancel_url,
            }}},
        }
        r = requests.post(
            f"{self.base}/v2/checkout/orders", json=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=25,
        )
        if not r.ok:
            raise PayPalError(f"PayPal order creation failed ({r.status_code}): {r.text[:400]}")
        return r.json()

    def get_order(self, order_id):
        token = self._token()
        r = requests.get(
            f"{self.base}/v2/checkout/orders/{order_id}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=25,
        )
        if not r.ok:
            raise PayPalError(f"PayPal order lookup failed ({r.status_code}): {r.text[:400]}")
        return r.json()

    def capture_order(self, order_id):
        token = self._token()
        r = requests.post(
            f"{self.base}/v2/checkout/orders/{order_id}/capture",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=25,
        )
        if not r.ok:
            raise PayPalError(f"PayPal capture failed ({r.status_code}): {r.text[:400]}")
        return r.json()
