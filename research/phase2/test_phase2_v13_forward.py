"""Pure offline tests — V1.3 frozen future-only research, no DB/network."""
import unittest
from datetime import datetime,timezone,timedelta
from decimal import Decimal as D

from phase2_v13_forward import (START,END,FINAL_HORIZON,SYMBOLS,
  utc,geometry,gates,regime,select_from_existing_scanner,
  first_full_hour,evaluate_closed_hourly,compare_original_checks)

def signal(sym="BTCUSDT",day="2026-11-15",hh="02:04:00",sid="s1",
           direction="SHORT",ep="100",sl="110",tp="90",checks=None,
           created=None,trade_permission=False):
    detected=f"{day}T{hh}+00:00"
    if created is None:created=f"{day}T02:04:15+00:00"
    return {"symbol":sym,"signal_id":sid,"detected_at_utc":detected,
            "created_at":created,"direction":direction,
            "entry_price":ep,"stop_loss":sl,"take_profit":tp,
            "trade_permission":trade_permission,"execution_checks":checks or {}}

def bars(start, *,mode="tp",direction="SHORT"):
    begin=first_full_hour(start)
    rows=[]
    for i in range(24):
        high,low=D("101"),D("99")
        if i==0:high,low=D("99"),D("95") # first bar does NOT touch entry 100
        if i==1:high,low=D("101"),D("99") # first clean entry touch
        if i==2:
            if mode=="tp":high,low=D("98"),D("89")
            if mode=="sl":high,low=D("111"),D("101")
            if mode=="ambiguous":high,low=D("111"),D("89")
        if mode=="no_entry":high,low=D("99"),D("95")
        if mode=="open" and i>=2:high,low=D("99"),D("95")
        rows.append({"t":(begin+timedelta(hours=i)).isoformat(),
                     "high":str(high),"low":str(low)})
    return rows

class FrozenV13Tests(unittest.TestCase):
    def test_window_is_forward_30_days(self):
        self.assertEqual((END-START).days,30)
        self.assertEqual(FINAL_HORIZON,(END+timedelta(days=1)))
        self.assertEqual(SYMBOLS,("BTCUSDT","ETHUSDT","SOLUSDT"))
    def test_utc_strict(self):
        with self.assertRaises(ValueError):utc("2026-11-15T01:00:00")
        with self.assertRaises(ValueError):utc("2026-11-15T01:00:00+01:00")
    def test_geometry_passes_both_directions(self):
        self.assertTrue(geometry(signal()))
        self.assertTrue(geometry(signal(direction="LONG",ep="100",sl="90",tp="110")))
        self.assertFalse(geometry(signal(ep="nan")))
        self.assertFalse(geometry(signal(direction="SHORT",ep="100",sl="90",tp="110")))
    def test_market_state_previous_completed_day(self):
        self.assertEqual(regime("102","100")["regime"],"RISING")
        self.assertEqual(regime("98","100")["regime"],"FALLING")
        self.assertEqual(regime("101","100")["regime"],"SIDEWAYS")
    def test_sort_ignores_future_performance_and_gate_success(self):
        early=signal(sid="early")
        later=signal(hh="20:04:00",sid="later",created="2026-11-15T20:04:20+00:00",
          checks={"rr_minimum_met":True,"participation_confirmed":True,
                  "momentum_confirmed":True})
        result=select_from_existing_scanner([later,early])
        self.assertEqual(result["selected_count"],1)
        self.assertEqual(result["selected"][0]["signal_id"],"early")
    def test_trading_permission_not_used_in_selection(self):
        x=signal(trade_permission=True)
        r=select_from_existing_scanner([x])
        self.assertEqual(r["selected_count"],1)
        self.assertEqual(r["selected"][0]["trade_permission"],True)
    def test_cross_midnight_24h_cooldown_suppresses_day(self):
        x=signal(day="2026-11-15",hh="23:04:00",sid="night",
            created="2026-11-15T23:04:20+00:00")
        y=signal(day="2026-11-16",hh="22:04:00",sid="nextday",
            created="2026-11-16T22:04:20+00:00")
        r=select_from_existing_scanner([x,y])
        self.assertEqual(r["selected_count"],1)
        day2=next(v for v in r["day_symbol_log"] if v["day"]=="2026-11-16" and v["symbol"]=="BTCUSDT")
        self.assertEqual(day2["status"],"COOLDOWN_SUPPRESSED")
    def test_candidate_after_day_after_cooldown_allowed(self):
        x=signal(day="2026-11-15",sid="first")
        y=signal(day="2026-11-17",sid="third",
            created="2026-11-17T02:04:20+00:00")
        self.assertEqual(select_from_existing_scanner([x,y])["selected_count"],2)
    def test_late_created_record_is_not_selected(self):
        x=signal(created="2026-11-15T03:00:05+00:00")
        self.assertEqual(select_from_existing_scanner([x])["selected_count"],0)
    def test_outside_preregistration_rejected(self):
        with self.assertRaises(ValueError):select_from_existing_scanner(
            [signal(day="2026-11-14")])
    def test_duplicate_id_fails_closed(self):
        with self.assertRaises(ValueError):select_from_existing_scanner([signal(),signal()])
    def test_filters_separate_permission_and_missingness(self):
        row=signal(checks={"rr_minimum_met":False,
                           "momentum_confirmed":True})
        x=gates(row)
        self.assertEqual(x["rr_minimum_met"],"FAIL")
        self.assertEqual(x["momentum_confirmed"],"PASS")
        self.assertEqual(x["participation_confirmed"],"MISSING")
        self.assertEqual(x["all_required_execution_checks"],"MISSING")
    def test_not_matured_means_pending(self):
        x=select_from_existing_scanner([signal()])["selected"][0]
        obs=evaluate_closed_hourly(x,bars(x["detected_at_utc"]),
            "2026-11-16T02:00:00+00:00",evidence_valid=True)
        self.assertEqual(obs["status"],"PENDING")
    def test_no_verified_market_evidence_is_unknown(self):
        x=select_from_existing_scanner([signal()])["selected"][0]
        obs=evaluate_closed_hourly(x,bars(x["detected_at_utc"]),
            "2026-11-17T00:00:00+00:00",evidence_valid=False)
        self.assertEqual(obs["status"],"UNKNOWN")
    def test_tp_outcome_remains_research_only_without_venue_cert(self):
        x=select_from_existing_scanner([signal()])["selected"][0]
        obs=evaluate_closed_hourly(x,bars(x["detected_at_utc"]),
            "2026-11-17T00:00:00+00:00",evidence_valid=True)
        self.assertEqual(obs["status"],"TP_FIRST")
        self.assertEqual(obs["historical_instrument_eligibility"],"UNKNOWN")
        self.assertEqual(obs["executed_fills"],0)
        self.assertGreater(D(obs["hypothetical_costs"]["fees_only"]["net_ex_funding_usdt"]),
                           D(obs["hypothetical_costs"]["baseline"]["net_ex_funding_usdt"]))
    def test_sl_and_ambiguous(self):
        x=select_from_existing_scanner([signal()])["selected"][0]
        for mode,expected in [("sl","SL_FIRST"),("ambiguous","AMBIGUOUS"),("no_entry","NO_ENTRY")]:
            obs=evaluate_closed_hourly(x,bars(x["detected_at_utc"],mode=mode),
               "2026-11-17T00:00:00+00:00",evidence_valid=True)
            self.assertEqual(obs["status"],expected)
            if mode in ("ambiguous","no_entry"):
                self.assertIsNone(obs["hypothetical_costs"]["baseline"])
    def test_invalid_hour_continuity_unknown(self):
        x=select_from_existing_scanner([signal()])["selected"][0]
        src=bars(x["detected_at_utc"]);src[7]["t"]=src[8]["t"]
        obs=evaluate_closed_hourly(x,src,"2026-11-17T00:00:00+00:00",evidence_valid=True)
        self.assertEqual(obs["status"],"UNKNOWN")
    def test_no_pass_group_not_comparable(self):
        x=select_from_existing_scanner([signal(checks={"rr_minimum_met":False})])["selected"][0]
        x["outcome"]={"status":"TP_FIRST","hypothetical_costs":{"baseline":{
            "net_ex_funding_usdt":"12"}}}
        r=compare_original_checks([x],"rr_minimum_met")
        self.assertEqual(r["comparison_status"],"NOT_COMPARABLE")
    def test_unknown_filter_rejected(self):
        with self.assertRaises(ValueError):compare_original_checks([],"fictional_filter")

if __name__=="__main__":unittest.main()
