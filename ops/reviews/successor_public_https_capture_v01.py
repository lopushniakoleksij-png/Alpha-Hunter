"""Successor research: one read-only HTTPS capture of a public futures quote.

Fixed endpoint only. No auth, orders, scanner imports or production writes.
TLS hostname validation authenticates the channel, NOT a signed venue quote.
"""
import hashlib
import json
import secrets
import ssl
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, HTTPSHandler, HTTPRedirectHandler, build_opener

from successor_forward_quote_transport_custody_v01 import build_transport_quote_capture

HOST = "api.bitget.com"
PATH = "/api/v2/mix/market/ticker"
SYMBOL = "BTCUSDT"
ALLOWED_INDEPENDENT_PUBLIC_SYMBOLS = frozenset(
    {"BTCUSDT", "NIGHTUSDT", "SOONUSDT"}
)
URL = "https://" + HOST + PATH + "?" + urlencode(
    {"symbol": SYMBOL, "productType": "USDT-FUTURES"}
)

class RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise ValueError("REDIRECT_FORBIDDEN")

def capture_public_quote(run_id, *, include_raw_bytes=False, symbol=SYMBOL):
    # Fixed public-market allowlist, explicitly not a universe scan.
    if type(symbol) is not str or symbol not in ALLOWED_INDEPENDENT_PUBLIC_SYMBOLS:
        raise ValueError("UNAPPROVED_INDEPENDENT_SYMBOL_PROBE")
    url = "https://" + HOST + PATH + "?" + urlencode(
        {"symbol": symbol, "productType": "USDT-FUTURES"}
    )
    ctx = ssl.create_default_context()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname
    opener = build_opener(HTTPSHandler(context=ctx), RejectRedirect())
    request = Request(url, headers={"Accept": "application/json"}, method="GET")
    with opener.open(request, timeout=8) as response:
        if response.status != 200 or response.geturl() != url:
            raise ValueError("VENUE_ENDPOINT_UNVERIFIED")
        if response.headers.get_content_type() != "application/json":
            raise ValueError("VENUE_CONTENT_TYPE_UNVERIFIED")
        payload = response.read(65537)
        captured_at = datetime.now(timezone.utc).isoformat()
    if not payload or len(payload) > 65536:
        raise ValueError("VENUE_RESPONSE_SIZE_INVALID")
    data = json.loads(payload)
    if (not isinstance(data, dict) or data.get("code") != "00000"
        or not isinstance(data.get("data"), list) or len(data["data"]) != 1):
        raise ValueError("VENUE_RESPONSE_UNVERIFIED")
    quote = build_transport_quote_capture(
        endpoint=PATH, requested_symbol=symbol, observed_at_utc=captured_at,
        transport_request_id=secrets.token_hex(12),
        raw_response_row=data["data"][0], upstream_call_succeeded=True,
        run_id=run_id
    )
    quote["response_sha256"] = hashlib.sha256(payload).hexdigest()
    quote["url"] = url
    quote["tls_host_checked"] = True
    quote["venue_price_signature_verified"] = False
    quote["source_inventory_authenticated"] = False
    quote["scientific_pass_permitted"] = False
    quote["trade_permission"] = False
    quote["exchange_authority"] = False
    # Optional research-only raw evidence for short-lived GitHub CI artifacts.
    # Does NOT prove venue-signed data, independent permanent custody, source
    # paper positions or any alert delivery. Default API remains unchanged.
    if include_raw_bytes is True:
        return quote, payload
    if include_raw_bytes is not False:
        raise ValueError("RAW_CAPTURE_FLAG_INVALID")
    return quote
