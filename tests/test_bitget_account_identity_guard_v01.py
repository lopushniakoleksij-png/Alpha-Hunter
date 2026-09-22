from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BITGET = ROOT / "alpha_hunter" / "bitget.py"
PRIVATE_ACCOUNT = ROOT / "alpha_hunter" / "private_account.py"
VERIFIER = ROOT / "ops" / "verify_bitget_48h_history_readonly.py"
COLLECTOR = ROOT / "alpha_hunter" / "collector.py"


def test_classic_identity_probe_uses_documented_read_only_account_info():
    text = BITGET.read_text(encoding="utf-8")
    assert '"/api/v2/spot/account/info"' in text
    assert "private=True" in text
    assert "spot_account_info_v2" in text


def test_account_identity_is_hashed_and_pinned_without_persisting_raw_uid():
    text = PRIVATE_ACCOUNT.read_text(encoding="utf-8")
    assert "BITGET_EXPECTED_ACCOUNT_FINGERPRINT" in text
    assert "hashlib.sha256" in text
    assert "ACCOUNT_IDENTITY_" in text
    assert '"userId"' in text
    assert '"account_identity_fingerprint"' in text
    assert '"account_identity_match"' in text
    assert '"user_id":' not in text


def test_48h_history_verifier_is_get_only_and_never_prints_raw_ids_or_secrets():
    text = VERIFIER.read_text(encoding="utf-8").lower()
    required = [
        "/api/v2/mix/order/fills",
        "/api/v2/mix/order/orders-history",
        "read_only_get",
        "no_order_write_path",
        "trade_permission",
        "account_identity_match",
    ]
    forbidden = [
        "requests.post",
        "requests.put",
        "requests.patch",
        "requests.delete",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        'row.get("orderid")',
        'row.get("tradeid")',
        "client.api_key",
        "client.secret_key",
        "client.passphrase",
    ]
    for marker in required:
        assert marker in text
    for marker in forbidden:
        assert marker not in text


def test_local_production_prefers_project_env_over_stale_inherited_credentials():
    text = COLLECTOR.read_text(encoding="utf-8")
    marker = 'load_env_file(\n        config_path.parent\n        / ".env",\n        override=True,\n    )'
    assert marker in text
