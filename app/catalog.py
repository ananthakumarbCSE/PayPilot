"""Multi-source product discovery for PayPilot.

DummyJSON is a public mock product API: useful for demos, not live inventory.
Optional eBay Browse API results are live marketplace listings and are view-only
because PayPilot does not have authority to complete purchases on eBay.
"""
from __future__ import annotations

import base64
import os
import re
import time
from decimal import Decimal, InvalidOperation
from typing import Any

import requests

from urllib.parse import quote

CATALOG = [
    {"id": "desk-lamp", "name": "Arc LED Desk Lamp", "category": "workspace", "price": "39.00",
     "description": "Dimmable warm/cool LED lamp with a compact metal base.", "tags": ["desk", "lamp", "lighting", "study"]},
    {"id": "keyboard", "name": "MechLite Wireless Keyboard", "category": "workspace", "price": "79.00",
     "description": "Low-profile mechanical keyboard with multi-device Bluetooth.", "tags": ["keyboard", "typing", "desk", "computer"]},
    {"id": "bottle", "name": "Flow 750ml Bottle", "category": "everyday", "price": "24.00",
     "description": "Insulated stainless-steel bottle for daily use.", "tags": ["bottle", "water", "travel", "fitness"]},
    {"id": "headphones", "name": "QuietWave Headphones", "category": "audio", "price": "129.00",
     "description": "Over-ear wireless headphones with active noise reduction.", "tags": ["audio", "music", "headphones", "travel"]},
    {"id": "notebook", "name": "Gridbound Project Notebook", "category": "stationery", "price": "12.00",
     "description": "Hardcover dotted notebook with 160 pages.", "tags": ["notebook", "writing", "study", "stationery"]},
    {"id": "webcam", "name": "ClearFrame HD Webcam", "category": "workspace", "price": "59.00",
     "description": "1080p USB webcam with privacy shutter.", "tags": ["camera", "webcam", "video", "computer"]},
]

_PRODUCT_CACHE: dict[str, dict[str, Any]] = {}
_EBAY_TOKEN: str | None = None
_EBAY_TOKEN_EXPIRES = 0.0
STOP_WORDS = {
    "i", "want", "need", "looking", "for", "buy", "me", "a", "an", "the", "please",
    "find", "show", "get", "purchase", "order", "under", "below", "less", "than",
    "with", "and", "or", "to", "my", "some", "best", "good", "recommend",
}


def _clean_query(query: str) -> str:
    text = re.sub(r"[$₹]\s*\d+(?:[.,]\d+)?", " ", (query or "").lower())
    text = re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:usd|dollars?)\b", " ", text)
    words = re.findall(r"[a-z0-9][a-z0-9+-]*", text)
    kept = [word for word in words if word not in STOP_WORDS and len(word) > 1 and not word.isdigit()]
    return " ".join(kept[:8]).strip()


def _local_search(query: str) -> list[dict]:
    terms = _clean_query(query).split()
    if not terms:
        return []
    scored = []
    for product in CATALOG:
        haystack = " ".join([
            product["name"], product["category"], product["description"], *product["tags"]
        ]).lower()
        score = sum(3 if term in product["name"].lower() else 1 for term in terms if term in haystack)
        if score:
            item = dict(product)
            item.update({
                "source": "PayPilot curated demo catalog",
                "source_type": "paypilot_demo",
                "checkout_eligible": True,
                "image": None,
                "source_url": None,
            })
            scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], Decimal(pair[1]["price"])))
    return [item for _, item in scored[:8]]


def _dummyjson_search(query: str) -> list[dict]:
    clean = _clean_query(query)
    if not clean:
        return []
    try:
        response = requests.get(
            "https://dummyjson.com/products/search",
            params={"q": clean, "limit": 20, "select": "id,title,description,category,price,brand,thumbnail,images,rating,availabilityStatus"},
            timeout=8,
            headers={"Accept": "application/json", "User-Agent": "PayPilot-Demo/1.0"},
        )
        response.raise_for_status()
        rows = response.json().get("products", [])
    except (requests.RequestException, ValueError, TypeError):
        return []

    results = []
    for row in rows:
        try:
            price = Decimal(str(row.get("price", 0))).quantize(Decimal("0.01"))
            if price <= 0:
                continue
            pid = f"dummyjson-{row['id']}"
            image = row.get("thumbnail") or (row.get("images") or [None])[0]
            item = {
                "id": pid,
                "name": str(row.get("title") or "Unnamed product")[:200],
                "category": str(row.get("category") or "general"),
                "price": f"{price:.2f}",
                "description": str(row.get("description") or "")[:500],
                "brand": str(row.get("brand") or ""),
                "tags": [],
                "source": "DummyJSON sample catalog",
                "source_type": "dummyjson_demo",
                "checkout_eligible": True,
                "image": image if isinstance(image, str) and image.startswith("https://") else None,
                "source_url": f"https://dummyjson.com/products/{row['id']}",
                "availability": str(row.get("availabilityStatus") or "Sample data; inventory not verified"),
                "rating": row.get("rating"),
            }
            _PRODUCT_CACHE[pid] = item
            results.append(item)
        except (InvalidOperation, KeyError, TypeError, ValueError):
            continue
    return results


def _ebay_access_token() -> str | None:
    global _EBAY_TOKEN, _EBAY_TOKEN_EXPIRES
    client_id = os.getenv("EBAY_CLIENT_ID", "").strip()
    client_secret = os.getenv("EBAY_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return None
    if _EBAY_TOKEN and time.time() < _EBAY_TOKEN_EXPIRES - 60:
        return _EBAY_TOKEN

    environment = os.getenv("EBAY_ENV", "production").strip().lower()
    host = "https://api.sandbox.ebay.com" if environment == "sandbox" else "https://api.ebay.com"
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    try:
        response = requests.post(
            f"{host}/identity/v1/oauth2/token",
            headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"},
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
        _EBAY_TOKEN = payload["access_token"]
        _EBAY_TOKEN_EXPIRES = time.time() + int(payload.get("expires_in", 7200))
        return _EBAY_TOKEN
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None


def _ebay_search(query: str) -> list[dict]:
    clean = _clean_query(query)
    token = _ebay_access_token()
    if not clean or not token:
        return []
    environment = os.getenv("EBAY_ENV", "production").strip().lower()
    host = "https://api.sandbox.ebay.com" if environment == "sandbox" else "https://api.ebay.com"
    marketplace = os.getenv("EBAY_MARKETPLACE_ID", "EBAY_US").strip() or "EBAY_US"
    try:
        response = requests.get(
            f"{host}/buy/browse/v1/item_summary/search",
            params={"q": clean, "limit": 12},
            headers={"Authorization": f"Bearer {token}", "X-EBAY-C-MARKETPLACE-ID": marketplace},
            timeout=10,
        )
        response.raise_for_status()
        rows = response.json().get("itemSummaries", [])
    except (requests.RequestException, ValueError, TypeError):
        return []

    results = []
    for row in rows:
        price_data = row.get("price") or {}
        currency = price_data.get("currency", "")
        # The PayPilot cart is USD-only. Keep non-USD listings view-only and do not
        # route them into the USD PayPal checkout.
        try:
            price = Decimal(str(price_data.get("value", "0"))).quantize(Decimal("0.01"))
        except InvalidOperation:
            continue
        if price <= 0:
            continue
        item_id = str(row.get("itemId") or "")
        if not item_id:
            continue
        image = (row.get("image") or {}).get("imageUrl")
        item = {
            "id": f"ebay-{item_id}",
            "name": str(row.get("title") or "eBay listing")[:200],
            "category": "marketplace",
            "price": f"{price:.2f}",
            "currency": currency or "USD",
            "description": str(row.get("condition") or "Marketplace listing"),
            "brand": "",
            "tags": [],
            "source": "eBay marketplace listing",
            "source_type": "ebay",
            "checkout_eligible": False,
            "image": image if isinstance(image, str) and image.startswith("https://") else None,
            "source_url": row.get("itemWebUrl"),
            "availability": "Check the seller's listing for current availability",
            "rating": None,
        }
        results.append(item)
    return results


def search_catalog(query: str, include_marketplace: bool = True) -> list[dict]:
    """Search local curated products plus external sample and optional live listings.

    No unrelated fallback products are returned when a query has no matches.
    """
    if not _clean_query(query):
        return []
    local = _local_search(query)
    sample = _dummyjson_search(query)
    marketplace = _ebay_search(query) if include_marketplace else []
    merged: list[dict] = []
    seen = set()
    for item in local + sample + marketplace:
        key = item["id"]
        if key not in seen:
            seen.add(key)
            merged.append(dict(item))

    # Respect common maximum-budget phrases when a USD-style amount is supplied.
    budget_match = re.search(
        r"(?:under|below|less than|max(?:imum)?|budget(?: of)?|up to)\s*[$]?\s*(\d+(?:[.,]\d{1,2})?)",
        (query or "").lower()
    )
    if budget_match:
        try:
            ceiling = Decimal(budget_match.group(1).replace(",", ""))
            merged = [
                item for item in merged
                if item.get("currency", "USD") == "USD" and Decimal(str(item["price"])) <= ceiling
            ]
        except (InvalidOperation, KeyError, TypeError):
            pass
    return merged[:24]


def get_product(product_id: str):
    cached = _PRODUCT_CACHE.get(product_id)
    if cached:
        # Live eBay listings are deliberately not eligible for PayPilot checkout.
        return dict(cached) if cached.get("checkout_eligible") else None
    return next(({
        **dict(product),
        "source": "PayPilot curated demo catalog",
        "source_type": "paypilot_demo",
        "checkout_eligible": True,
        "image": None,
        "source_url": None,
    } for product in CATALOG if product["id"] == product_id), None)
