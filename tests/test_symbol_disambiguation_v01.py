from pathlib import Path

import app as dashboard_app


def test_leading_zero_symbol_is_explicit():
    assert dashboard_app.symbol_label("0GUSDT") == "0GUSDT (ZERO-G)"


def test_letter_o_symbol_is_unchanged():
    assert dashboard_app.symbol_label("OGUSDT") == "OGUSDT"


def test_non_ambiguous_symbols_are_unchanged():
    assert dashboard_app.symbol_label("BTCUSDT") == "BTCUSDT"
    assert dashboard_app.symbol_label(None) == ""


def test_money_action_and_freeze_surfaces_use_symbol_label_filter():
    source = Path("app.py").read_text(encoding="utf-8")

    assert "{{ row.symbol|symbol_label }} {{ a.direction }}" in source
    assert "{{ s.symbol|symbol_label }}" in source
    assert "{{ c.symbol|symbol_label }}" in source
    assert "{{ frozen.symbol|symbol_label }}" in source
    assert "{{ f.symbol|symbol_label }}" in source
