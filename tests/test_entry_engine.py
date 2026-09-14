import unittest

from alpha_hunter.entry_engine import (
    EntryInputs,
    EntryState,
    EntryStatus,
    Side,
    evaluate_entry,
    transition_entry_state,
)


def long_inputs(**overrides):
    values = {
        "symbol": "TESTUSDT",
        "side": Side.LONG,
        "anchor": 100.0,
        "trigger_extreme": 100.9,
        "pullback_extreme": 100.2,
        "atr_5m": 10.0,
        "spread": 0.05,
        "tick_size": 0.1,
        "current_price": 101.0,
        "structural_target": 105.5,
        "estimated_round_trip_cost": 0.2,
        "data_fresh": True,
        "direction_eligible": True,
        "direction_change_clear": True,
        "conflict_firewall_clear": True,
        "liquidity_executable": True,
        "price_accepted": True,
        "aggressive_flow_confirmed": True,
        "open_interest_confirmed": True,
        "order_book_confirmed": False,
    }
    values.update(overrides)
    return EntryInputs(**values)


class EntryEngineTests(unittest.TestCase):
    def test_long_ready_has_exact_geometry_but_no_trade_permission(self):
        result = evaluate_entry(long_inputs())
        self.assertEqual(result.status, EntryStatus.READY.value)
        self.assertEqual(result.state, EntryState.READY.value)
        self.assertEqual(result.entry, 101.0)
        self.assertEqual(result.stop, 99.2)
        self.assertGreaterEqual(result.net_rr, 2.20)
        self.assertTrue(result.shadow_only)
        self.assertFalse(result.trade_permission)

    def test_short_rules_are_mirrored(self):
        result = evaluate_entry(
            long_inputs(
                side=Side.SHORT,
                trigger_extreme=99.1,
                pullback_extreme=99.8,
                current_price=99.0,
                structural_target=94.5,
                aggressive_flow_confirmed=True,
                open_interest_confirmed=False,
                order_book_confirmed=True,
            )
        )
        self.assertEqual(result.status, EntryStatus.READY.value)
        self.assertEqual(result.entry, 99.0)
        self.assertEqual(result.stop, 100.8)
        self.assertFalse(result.trade_permission)

    def test_wide_stop_is_hard_veto(self):
        result = evaluate_entry(long_inputs(pullback_extreme=90.0))
        self.assertEqual(result.status, EntryStatus.NO.value)
        self.assertIn("stop_too_wide", result.hard_vetoes)

    def test_weak_net_rr_is_hard_veto(self):
        result = evaluate_entry(long_inputs(structural_target=103.0))
        self.assertEqual(result.status, EntryStatus.NO.value)
        self.assertIn("net_rr_below_2.20", result.hard_vetoes)

    def test_entry_outside_band_is_rejected(self):
        result = evaluate_entry(long_inputs(trigger_extreme=103.0, current_price=103.1))
        self.assertEqual(result.status, EntryStatus.NO.value)
        self.assertIn("outside_entry_band_or_chased", result.hard_vetoes)

    def test_late_chase_is_rejected_even_inside_wider_band(self):
        result = evaluate_entry(long_inputs(current_price=101.6))
        self.assertEqual(result.status, EntryStatus.NO.value)
        self.assertIn("outside_entry_band_or_chased", result.hard_vetoes)

    def test_missing_acceptance_stays_armed(self):
        result = evaluate_entry(long_inputs(price_accepted=False))
        self.assertEqual(result.status, EntryStatus.WATCH.value)
        self.assertEqual(result.state, EntryState.ARMED.value)
        self.assertFalse(result.trade_permission)

    def test_one_confirmation_stays_watch(self):
        result = evaluate_entry(
            long_inputs(open_interest_confirmed=False, order_book_confirmed=False)
        )
        self.assertEqual(result.status, EntryStatus.WATCH.value)
        self.assertEqual(result.confirmation_count, 1)

    def test_stale_data_can_never_be_ready(self):
        result = evaluate_entry(long_inputs(data_fresh=False))
        self.assertEqual(result.status, EntryStatus.NO.value)
        self.assertIn("stale_or_incomplete_data", result.hard_vetoes)

    def test_state_machine_requires_each_stage(self):
        state = EntryState.DISCOVERED
        for event, expected in (
            ("impulse_confirmed", EntryState.IMPULSE_CONFIRMED),
            ("pullback_started", EntryState.PULLBACK),
            ("geometry_armed", EntryState.ARMED),
            ("trigger_ready", EntryState.READY),
            ("entered", EntryState.ENTERED),
            ("closed", EntryState.CLOSED),
        ):
            state = transition_entry_state(state, event)
            self.assertEqual(state, expected)

    def test_state_machine_rejects_direct_jump_to_ready(self):
        with self.assertRaises(ValueError):
            transition_entry_state(EntryState.DISCOVERED, "trigger_ready")

    def test_terminal_state_cannot_reactivate(self):
        self.assertEqual(
            transition_entry_state(EntryState.EXPIRED, "impulse_confirmed"),
            EntryState.EXPIRED,
        )


if __name__ == "__main__":
    unittest.main()
