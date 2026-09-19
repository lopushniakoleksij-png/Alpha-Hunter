from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops" / "verify_main_account_readonly.py"


def test_cutover_verifier_exists_and_is_get_only_by_construction():
    text = SCRIPT.read_text(encoding="utf-8").lower()

    required = [
        "readonlyfillclient",
        "collect_private_account_snapshot",
        "collect_fill_traceability_with_historical_diagnostic",
        "trade_permission",
        "no_order_write_path",
        "secret_values_printed",
    ]
    forbidden = [
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "requests.post",
        "requests.put",
        "requests.delete",
    ]

    for marker in required:
        assert marker in text
    for marker in forbidden:
        assert marker not in text


def test_cutover_verifier_never_prints_credentials_or_raw_trade_ids():
    text = SCRIPT.read_text(encoding="utf-8")

    forbidden = [
        'client.api_key',
        'client.secret_key',
        'client.passphrase',
        'item.get("trade_id")',
        'item.get("order_id")',
    ]
    for marker in forbidden:
        assert marker not in text
