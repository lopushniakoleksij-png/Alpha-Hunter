/* Alpha Hunter V8 UI-only enhancement.
 * Reorganizes existing server-rendered evidence without modifying market data,
 * scoring, execution gates, source selection, APIs or scanner processes.
 * Does not fetch any endpoints or run scans. No live order controls.
 */
(() => {
  "use strict";
  const byId = (id) => document.getElementById(id);
  const body = document.body;
  const workspace = byId("v8-workspace");
  if (!body || !body.classList.contains("v8-body") || !workspace) return;

  const names = ["overview", "research", "results", "system"];
  const panes = Object.fromEntries(names.map(n => [n, byId("v8-view-" + n)]));
  if (Object.values(panes).some(node => !node)) return;

  // Only move presentation components. Server-rendered evidence, source
  // timestamps and original table cells remain unchanged in the same DOM.
  for (const node of [...document.querySelectorAll("[data-v8-section]")]) {
    const name = node.getAttribute("data-v8-section");
    const target = panes[name];
    if (target && node !== target) target.appendChild(node);
  }
  body.classList.add("v8-enhanced");
  workspace.classList.add("v8-enhanced");

  const matrix = document.querySelector(".v8-strategy-table");
  const cards = byId("v8-mobile-cards");
  const loadMore = byId("v8-load-more");
  const resultCount = byId("v8-result-count");
  const search = byId("v8-search");
  const statusFilter = byId("v8-status");
  const sideFilter = byId("v8-side");
  const strategyFilter = byId("v8-strategy");
  const reset = byId("v8-reset");
  const detailPanel = byId("v8-detail-panel");

  let pageSize = 24, visibleLimit = pageSize;
  let activeDetails = -1;
  let filteredRows = [];
  const allRows = [];

  // Fixed 14-column source contract already rendered by Jinja. Keep source
  // strings intact and preserve all values and the original row order.
  if (matrix) {
    const trs = [...matrix.querySelectorAll("tbody tr")];
    trs.forEach((tr, index) => {
      const cells = [...tr.querySelectorAll("td")];
      if (cells.length !== 14) return;
      const txt = n => (cells[n]?.textContent || "").trim();
      const record = {
        index, tr,
        symbol: txt(0), strategy: txt(1), status: txt(2),
        persistence: txt(3), scans: txt(4), side: txt(5),
        gate: txt(6), intent: txt(7), score: txt(8),
        entry: txt(9), stop: txt(10), target: txt(11),
        rr: txt(12), blocker: txt(13),
      };
      // Presentation-only label; do not write to canonical source evidence.
      cells[3].textContent = record.persistence + " · " + record.scans + " scans";
      allRows.push(record);
      const btn = cells[0].querySelector(".v8-open-research");
      if (btn) {
        btn.addEventListener("click", () => {
          activeDetails = activeDetails === record.index ? -1 : record.index;
          showDesktopDetails();
        });
      }
    });
  }

  function make(tag, className, value) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (value !== undefined && value !== null) el.textContent = String(value);
    return el;
  }
  function statusLabel(raw) { return raw || "UNAVAILABLE"; }
  function describeGate(rec) {
    if (rec.status === "WATCH") return "WATCH — strategy setup only, not executable";
    if (rec.status === "SHADOW_CANDIDATE") return "Shadow candidate — final paper gate still applies";
    return "Final paper gate: " + (rec.gate || "UNKNOWN");
  }
  function formatDisplayPrice(raw) {
    if (!raw || raw === "—") return "—";
    const n = Number(raw);
    if (!Number.isFinite(n)) return raw;
    if (n === 0) return "0";
    // Visual rounding only. Original string remains visible in full detail.
    return new Intl.NumberFormat("en-GB", {
      maximumSignificantDigits: 7, useGrouping: n >= 1000,
    }).format(n);
  }
  function detailField(label, raw, showExact = false) {
    const wrap = make("div", "v8-detail-field");
    const name = make("dt", "", label);
    const desc = make("dd", "", showExact ? formatDisplayPrice(raw) : (raw || "—"));
    wrap.append(name, desc);
    if (showExact && raw && raw !== "—") {
      const exact = make("span", "v8-exact", "Exact: " + raw);
      wrap.append(exact);
    }
    return wrap;
  }
  function buildDetail(rec) {
    const box = document.createDocumentFragment();
    const grid = make("dl", "v8-detail-grid");
    grid.append(
      detailField("Entry · hypothetical", rec.entry, true),
      detailField("Stop · hypothetical", rec.stop, true),
      detailField("Target · hypothetical", rec.target, true),
      detailField("Raw R:R (uncalibrated)", rec.rr),
      detailField("Raw shadow score (not probability)", rec.score),
      detailField("Final paper gate", rec.gate),
      detailField("Raw setup intent", rec.intent),
      detailField("Strategy persistence", rec.persistence + " · " + rec.scans + " scans"),
    );
    box.append(grid);
    const warning = make("p", "v8-detail-warning",
      (rec.blocker || describeGate(rec)) +
      " · This row is research-only; no exchange order authority is granted.");
    box.append(warning);
    const footer = make("p", "v8-archive-notice",
      "Original values are preserved. Hypothetical setup prices are not executable trading instructions.");
    box.append(footer);
    return box;
  }

  function showDesktopDetails() {
    if (!detailPanel) return;
    allRows.forEach(r => r.tr.classList.toggle("v8-row-selected", r.index === activeDetails));
    detailPanel.replaceChildren();
    if (activeDetails < 0 || !allRows.some(r => r.index === activeDetails)) {
      detailPanel.hidden = true;
      return;
    }
    const rec = allRows.find(r => r.index === activeDetails);
    const top = make("div", "v8-detail-top");
    const title = make("h3", "", rec.symbol + " · " + rec.strategy);
    const close = make("button", "v8-copy", "Close details");
    close.type = "button";
    close.addEventListener("click", () => {activeDetails = -1;showDesktopDetails();});
    top.append(title, close);
    const gate = make("p", "v8-archive-notice",
      statusLabel(rec.status) + " · " + describeGate(rec) + " · No real-money execution");
    detailPanel.append(top, gate, buildDetail(rec));
    detailPanel.hidden = false;
  }

  const unique = (key) => [...new Set(allRows.map(r => r[key]).filter(Boolean))].sort();
  function fillSelect(select, values) {
    if (!select) return;
    for (const value of values) {
      const option = make("option", "", value);
      option.value = value;
      select.appendChild(option);
    }
  }
  fillSelect(statusFilter, unique("status"));
  fillSelect(sideFilter, unique("side"));
  fillSelect(strategyFilter, unique("strategy"));

  function matchRows() {
    const query = (search?.value || "").trim().toLowerCase();
    const status = statusFilter?.value || "";
    const side = sideFilter?.value || "";
    const strategy = strategyFilter?.value || "";
    return allRows.filter(rec =>
      (!query || (rec.symbol + " " + rec.strategy).toLowerCase().includes(query)) &&
      (!status || rec.status === status) &&
      (!side || rec.side === side) &&
      (!strategy || rec.strategy === strategy)
    );
  }

  function mobileCard(rec) {
    const article = make("article", "v8-mobile-card");
    const btn = make("button", "v8-card-toggle");
    btn.type = "button";
    btn.setAttribute("aria-expanded", "false");
    btn.setAttribute("aria-label", rec.symbol + " " + rec.strategy + ". " + statusLabel(rec.status) + ". Open research details");
    const details = make("div", "v8-card-expanded");
    const contentId = "v8-card-details-" + rec.index;
    details.id = contentId;
    details.hidden = true;
    btn.setAttribute("aria-controls", contentId);
    const row = make("div", "v8-card-heading");
    const info = make("div", "");
    info.append(make("div", "v8-card-pair", rec.symbol), make("div", "v8-card-strategy", rec.strategy));
    row.append(info, make("span", "v8-card-status", statusLabel(rec.status)));
    const metrics = make("div", "v8-card-metrics");
    metrics.append(
      make("span", "", rec.side || "NO SIDE"),
      make("span", "", "Raw R:R " + (rec.rr || "—")),
      make("span", "", rec.persistence + " · " + rec.scans + " scans"),
    );
    const gate = make("div", "v8-card-gate", describeGate(rec) + "  ·  Details ▾");
    btn.append(row, metrics, gate);
    details.append(buildDetail(rec));
    btn.addEventListener("click", () => {
      const open = details.hidden;
      details.hidden = !open;
      btn.setAttribute("aria-expanded", String(open));
    });
    article.append(btn, details);
    return article;
  }

  function renderMobile() {
    if (!cards) return;
    const shown = filteredRows.slice(0, visibleLimit);
    const frag = document.createDocumentFragment();
    for (const rec of shown) frag.appendChild(mobileCard(rec));
    if (shown.length === 0) {
      frag.appendChild(make("p", "v8-archive-notice",
        allRows.length ? "No research entries match the selected filters." : "No S1–S10 observations in this verified scan."));
    }
    cards.replaceChildren(frag);
    if (loadMore) {
      loadMore.hidden = shown.length >= filteredRows.length;
      loadMore.textContent = "Show more research (" + shown.length + " of " + filteredRows.length + ")";
    }
  }

  function applyFilters() {
    filteredRows = matchRows();
    for (const rec of allRows) rec.tr.hidden = !filteredRows.includes(rec);
    if (resultCount) resultCount.textContent =
      filteredRows.length + " research observations · " + allRows.length +
      " total · No real-money execution permission";
    if (activeDetails >= 0 && !filteredRows.some(r => r.index === activeDetails)) {
      activeDetails = -1;
      showDesktopDetails();
    }
    visibleLimit = pageSize;
    renderMobile();
  }
  for (const input of [statusFilter, sideFilter, strategyFilter]) {
    input?.addEventListener("change", applyFilters);
  }
  search?.addEventListener("input", applyFilters);
  reset?.addEventListener("click", () => {
    if (search) search.value = "";
    for (const el of [statusFilter, sideFilter, strategyFilter]) if (el) el.value = "";
    applyFilters();
    search?.focus();
  });
  loadMore?.addEventListener("click", () => {
    visibleLimit += pageSize;
    renderMobile();
  });

  // Secondary operations tables may scroll inside their panel but never
  // extend document width. The primary research matrix becomes cards.
  for (const table of document.querySelectorAll("table:not(.v8-strategy-table)")) {
    if (table.parentElement?.classList.contains("v8-ops-table-scroll")) continue;
    const wrapper = make("div", "v8-ops-table-scroll");
    table.parentNode?.insertBefore(wrapper, table);
    wrapper.appendChild(table);
  }

  function activate(tab, setHash = true) {
    if (!names.includes(tab)) return;
    for (const name of names) {
      panes[name].classList.toggle("is-active", name === tab);
      panes[name].hidden = name !== tab;
    }
    for (const button of document.querySelectorAll("[data-v8-tab]")) {
      const selected = button.getAttribute("data-v8-tab") === tab;
      if (selected) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    }
    if (setHash) history.replaceState(null, "", "#v8-" + tab);
    if (tab === "research") applyFilters();
    window.scrollTo({top:0, behavior:"instant"});
  }
  for (const button of document.querySelectorAll("[data-v8-tab]")) {
    button.addEventListener("click", () => activate(button.getAttribute("data-v8-tab")));
  }
  window.addEventListener("hashchange", () => {
    const name = location.hash.replace(/^#v8-/, "");
    if (names.includes(name)) activate(name, false);
  });
  applyFilters();
  const initialTab = location.hash.startsWith("#v8-") ? location.hash.slice(4) : "overview";
  activate(names.includes(initialTab) ? initialTab : "overview", false);
})();
