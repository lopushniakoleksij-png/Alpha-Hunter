PERFORMANCE_PAGE = r"""
<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Alpha Hunter V3 Intelligence</title>
<style>
:root{--bg:#071018;--panel:#0d1822;--line:#1c2c39;--text:#e8f0f6;--muted:#8ea1b2;--green:#24d18f;--red:#ff6474;--blue:#4db6ff;--amber:#ffbf47}
*{box-sizing:border-box}body{margin:0;background:linear-gradient(180deg,#050b11,#09131c);color:var(--text);font-family:Inter,system-ui,-apple-system,sans-serif}
.wrap{max-width:1500px;margin:auto;padding:24px}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}.top a{color:var(--blue);text-decoration:none}
h1{margin:0}.sub{color:var(--muted);margin-top:6px}.grid{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-bottom:18px}
.card,.panel{background:var(--panel);border:1px solid var(--line);border-radius:16px}.card{padding:18px}
.label{font-size:12px;text-transform:uppercase;color:var(--muted)}.value{font-size:27px;font-weight:800;margin-top:6px}.panel{padding:18px;margin-bottom:18px;overflow:auto}
table{width:100%;border-collapse:collapse;font-size:13px}th{text-align:left;color:var(--muted);padding:10px 8px;border-bottom:1px solid var(--line)}td{padding:11px 8px;border-bottom:1px solid #142431;white-space:nowrap}
.good{color:var(--green)}.bad{color:var(--red)}.warn{color:var(--amber)}.pill{padding:4px 8px;border:1px solid var(--line);border-radius:999px;font-size:11px}
.controls{display:flex;gap:8px;margin-bottom:18px}.controls a{color:var(--text);text-decoration:none;padding:8px 12px;border:1px solid var(--line);border-radius:10px}.controls a.active{border-color:var(--blue);color:var(--blue)}
.two{display:grid;grid-template-columns:1.25fr .75fr;gap:18px}.note{color:var(--muted);font-size:12px;margin-top:8px}
@media(max-width:1000px){.grid{grid-template-columns:repeat(2,1fr)}.two{grid-template-columns:1fr}.wrap{padding:14px}}
</style></head><body><div class="wrap">
<div class="top"><div><h1>Alpha Hunter V3 Intelligence</h1><div class="sub">Statistical decision engine — recommendations only, no automatic live weight changes</div></div><a href="/">← Scanner</a></div>
<div class="controls">{% for h in [1,4,12,24] %}<a class="{{ 'active' if data.horizon_hours==h else '' }}" href="/performance?horizon={{h}}">{{h}}H</a>{% endfor %}</div>

<div class="grid">
<div class="card"><div class="label">Samples</div><div class="value">{{data.overall.samples}}</div></div>
<div class="card"><div class="label">Directional Accuracy</div><div class="value">{{data.overall.directional_accuracy}}%</div><div class="note">CI {{data.overall.accuracy_ci_low}}–{{data.overall.accuracy_ci_high}}%</div></div>
<div class="card"><div class="label">Expected Value</div><div class="value {{'good' if data.overall.expected_value_pct >= 0 else 'bad'}}">{{data.overall.expected_value_pct}}%</div></div>
<div class="card"><div class="label">Profit Factor</div><div class="value">{{data.overall.profit_factor}}</div></div>
<div class="card"><div class="label">Big-Move Hit Rate</div><div class="value">{{data.overall.big_move_rate}}%</div></div>
</div>

<div class="two">
<div class="panel"><h2>Institutional Strategy Ranking</h2>
<table><thead><tr><th>State</th><th>N</th><th>Accuracy</th><th>95% CI</th><th>EV</th><th>PF</th><th>Payoff</th><th>Coverage</th></tr></thead><tbody>
{% for r in data.strategies %}
<tr><td><b>{{r.name}}</b></td><td>{{r.samples}}</td><td>{{r.directional_accuracy}}%</td><td>{{r.accuracy_ci_low}}–{{r.accuracy_ci_high}}%</td>
<td class="{{'good' if r.expected_value_pct>=0 else 'bad'}}">{{r.expected_value_pct}}%</td><td>{{r.profit_factor}}</td><td>{{r.payoff_ratio}}</td><td>{{r.coverage_pct}}%</td></tr>
{% endfor %}</tbody></table></div>

<div class="panel"><h2>Decision Recommendations</h2>
<table><thead><tr><th>Strategy</th><th>Action</th><th>Reason</th></tr></thead><tbody>
{% for r in data.recommendations %}<tr><td><b>{{r.strategy}}</b></td><td><span class="pill">{{r.action}}</span></td><td>{{r.reason}}</td></tr>{% endfor %}
</tbody></table>
<div class="note">Promotion requires {{data.methodology.promotion_samples}} samples, positive EV, 95% CI floor ≥52%, and profit factor ≥1.20.</div></div>
</div>

<div class="two">
<div class="panel"><h2>Score Calibration</h2>
<table><thead><tr><th>Score</th><th>N</th><th>Accuracy</th><th>EV</th><th>PF</th></tr></thead><tbody>
{% for r in data.score_buckets %}<tr><td>{{r.name}}</td><td>{{r.samples}}</td><td>{{r.directional_accuracy}}%</td><td class="{{'good' if r.expected_value_pct>=0 else 'bad'}}">{{r.expected_value_pct}}%</td><td>{{r.profit_factor}}</td></tr>{% endfor %}
</tbody></table></div>

<div class="panel"><h2>Confidence Calibration</h2>
<table><thead><tr><th>Confidence</th><th>N</th><th>Actual Accuracy</th><th>EV</th><th>PF</th></tr></thead><tbody>
{% for r in data.confidence_buckets %}<tr><td>{{r.name}}</td><td>{{r.samples}}</td><td>{{r.directional_accuracy}}%</td><td class="{{'good' if r.expected_value_pct>=0 else 'bad'}}">{{r.expected_value_pct}}%</td><td>{{r.profit_factor}}</td></tr>{% endfor %}
</tbody></table></div>
</div>
</div></body></html>
"""
