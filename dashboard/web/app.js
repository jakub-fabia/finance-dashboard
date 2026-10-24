// Renders dashboard.json (written by dashboard/build_dashboard.py). No maths
// beyond presentation happens here.
"use strict";

// Holdings carry their colour slot (dashboard.json); 0 = more holdings than hues.
const holdingColor = (h) => h.slot ? `var(--s${h.slot})` : "var(--bar)";
const PERIODS = [["1d", "Day"], ["7d", "Week"], ["30d", "Month"], ["365d", "Year"]];
// Spending categories → categorical slot (fixed: the colour follows the
// category, never its rank). Eight hues; the small ones stay neutral.
const CAT_SLOTS = {
  rent: 7, groceries: 3, eatout: 2, leisure: 5,
  transportation: 1, subscriptions: 4, shopping: 8, travel: 6,
};
const catColor = (cat) => CAT_SLOTS[cat] ? `var(--s${CAT_SLOTS[cat]})` : "var(--bar)";
const RANGES = [[7, "1W"], [30, "1M"], [91, "3M"], [365, "1Y"], [0, "All"]];
const RECENT_STEP = 8;
// Treasury bond series, longest first; anything else follows in name order.
const BOND_TYPES = {
  EDO: "10-year, inflation-linked",
  ROD: "12-year family, inflation-linked",
  ROS: "6-year family, inflation-linked",
  COI: "4-year, inflation-linked",
  TOS: "3-year, fixed rate",
  DOR: "2-year, NBP rate",
  ROR: "1-year, NBP rate",
  OTS: "3-month, fixed rate",
};

const $ = (id) => document.getElementById(id);
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
};

const nf = (d) => new Intl.NumberFormat("pl-PL", { minimumFractionDigits: d, maximumFractionDigits: d });
const NF0 = nf(0), NF2 = nf(2);
// Every absolute number goes through num(): with amounts hidden it's a fixed
// mask, so neither the value nor its length leaks. Percentages stay visible.
const MASK = "••••";
const num = (v, d = 0) => state.hidden ? MASK : (d ? NF2 : NF0).format(v);
const money = (v, d = 2) => `${num(v, d)} zł`;
// Polarity is the sign, never colour: "+1 234,56 zł" / "−1 234,56 zł".
const signed = (v, d = 2) => `${v > 0 ? "+" : v < 0 ? "−" : "±"}${money(Math.abs(v), d)}`;
// Whole złoty once the grosze stop mattering.
const signedShort = (v) => signed(v, Math.abs(v) < 100 ? 2 : 0);
const pct = (v) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${NF2.format(Math.abs(v))}%`;
const dayFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short" });
const dateFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" });
const monYearFmt = new Intl.DateTimeFormat("en-GB", { month: "short", year: "numeric" });
const timeFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
// Chart times are Warsaw wall-clock seconds stored as if UTC.
const wallFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "UTC" });
const monthFmt = new Intl.DateTimeFormat("en-GB", { month: "long", year: "numeric" });
const monthName = new Intl.DateTimeFormat("en-GB", { month: "long" });
const monthDate = (m) => new Date(`${m}-01T12:00:00`);
const day = (iso) => new Date(`${iso}T12:00:00`);

let D = null;
const state = { hidden: false, range: 91, month: 0, recent: RECENT_STEP, openCat: null, openHolding: null };

// --- Controls ---------------------------------------------------------------

function segmented(container, options, current, onPick) {
  container.replaceChildren();
  for (const [value, label] of options) {
    const b = el("button", "", label);
    b.type = "button";
    b.setAttribute("role", "radio");
    b.setAttribute("aria-checked", String(value === current));
    b.addEventListener("click", () => {
      container.querySelectorAll("button").forEach((x) => x.setAttribute("aria-checked", String(x === b)));
      onPick(value);
    });
    container.append(b);
  }
  container.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const btns = [...container.querySelectorAll("button")];
    const i = btns.indexOf(document.activeElement);
    if (i < 0) return;
    const next = btns[(i + (e.key === "ArrowRight" ? 1 : btns.length - 1)) % btns.length];
    next.focus();
    next.click();
  });
}

// Two-line row used by every list: name / amount, then meta / secondary.
function row(cls, name, amount, meta, side) {
  const r = el("span", `row ${cls || ""}`);
  const n = el("span", "r-name");
  n.append(...[name].flat());
  r.append(n, el("span", "r-amt", amount));
  if (meta !== undefined || side !== undefined) r.append(el("span", "r-meta", meta || ""), el("span", "r-side", side || ""));
  return r;
}

// --- Balance ----------------------------------------------------------------

function renderBalance() {
  const nw = D.net_worth;
  $("nw-value").replaceChildren(num(nw.value, 2), " ", el("span", "cur", "zł"));
  $("nw-profit").textContent = `${signedShort(nw.profit)} earned in total · ${pct(nw.profit / nw.cost * 100)}`;

  const earned = $("earned");
  earned.replaceChildren(...PERIODS.map(([key, label]) => {
    const d = el("div");
    d.append(el("dt", "", label), el("dd", "", signedShort(D.changes[key].profit)));
    return d;
  }));

  const alloc = $("alloc");
  alloc.replaceChildren();
  const parts = D.holdings.filter((h) => h.value > 0);
  alloc.setAttribute("aria-label", parts.map((h) => `${h.label} ${Math.round(h.value / nw.value * 100)}%`).join(", "));
  for (const h of parts) {
    const s = el("span");
    s.style.flex = String(h.value);
    s.style.background = holdingColor(h);
    s.title = `${h.label}: ${money(h.value, 0)} (${NF0.format(h.value / nw.value * 100)}%)`;
    alloc.append(s);
  }

  const details = { stocks: stocksDetail, bonds: bondsDetail };
  const list = $("holdings");
  list.replaceChildren();
  for (const h of D.holdings) {
    const li = el("li");
    const open = state.openHolding === h.key;
    const head = el(details[h.key] ? "button" : "div", "h-row");
    const sw = el("span", "swatch");
    sw.style.background = holdingColor(h);
    head.append(sw, row("", h.label, money(h.value, 0), "",
      h.profit ? `${signedShort(h.profit)} · ${pct(h.profit_pct)}` : "—"));
    if (details[h.key]) {
      head.type = "button";
      head.setAttribute("aria-expanded", String(open));
      head.append(el("span", "chev", ""));
      head.addEventListener("click", () => {
        state.openHolding = open ? null : h.key;
        renderBalance();
      });
    }
    li.append(head);
    if (open) li.append(details[h.key](h));
    list.append(li);
  }
}

function stocksDetail(h) {
  const box = el("div", "h-detail");
  let open = 0;
  for (const a of D.stock_accounts) {
    const g = el("div", "group");
    g.append(row("g-head", [a.label, share(a.value, h.value)], money(a.value, 0)));
    for (const p of a.positions) {
      open += p.profit;
      // "Example World Index UCITS ETF (Acc)" → "Example World Index".
      const short = p.name.replace(/\s+UCITS ETF.*$/i, "");
      const r = row("", short, money(p.value, 0),
        `${p.ticker.split(".")[0]} · ${num(p.qty, 2)} units`,
        `${signedShort(p.profit)} · ${pct(p.profit_pct)}`);
      r.title = `${p.name}: ${num(p.qty, 2)} × ${NF2.format(p.price)} ${p.currency}`;
      g.append(r);
    }
    if (Math.abs(a.cash) >= 1) g.append(row("", "Cash", money(a.cash, 0)));
    box.append(g);
  }
  // All-time profit = open positions + everything already closed.
  const g = el("div", "group");
  g.append(row("g-foot", "Sold positions, dividends, fees", signedShort(h.profit - open)));
  box.append(g);
  return box;
}

// "· 41%" after a group's name: its part of the holding.
const share = (part, whole) => el("span", "share", ` ${NF0.format(whole ? part / whole * 100 : 0)}%`);

function bondsDetail(h) {
  const box = el("div", "h-detail");
  const types = [...new Set(D.bonds.map((b) => b.type))].sort((a, b) => {
    const order = Object.keys(BOND_TYPES);
    const ia = order.indexOf(a), ib = order.indexOf(b);
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a.localeCompare(b);
  });
  for (const type of types) {
    const bonds = D.bonds.filter((b) => b.type === type);
    const sum = (k) => bonds.reduce((s, b) => s + b[k], 0);
    const g = el("div", "group");
    g.append(row("g-head", [type, share(sum("value"), h.value)], money(sum("value"), 0), BOND_TYPES[type] || "Treasury bonds",
      signedShort(sum("accrued"))));
    for (const b of bonds) {
      const matures = b.maturity ? day(b.maturity) : null;
      // Within two months the money needs a decision: give the exact day.
      const soon = matures && (matures - Date.now()) / 864e5 <= 60;
      const span = !matures ? "" : soon ? `matures ${dateFmt.format(matures)}`
        : `${monYearFmt.format(day(b.purchase))} → ${monYearFmt.format(matures)}`;
      const r = row(soon ? "soon" : "", b.name.split("/")[0], money(b.value, 0),
        `${NF2.format(b.rate)}% · ${span}`, signedShort(b.accrued));
      r.title = `${b.name}: bought ${dateFmt.format(day(b.purchase))} for ${money(b.nominal, 0)}, rate ${b.rate_source}`;
      g.append(r);
    }
    box.append(g);
  }
  return box;
}

// --- Stocks chart -------------------------------------------------------------

let chart = null, series = null, chartValues = new Map(), chartLegendBound = false, show = null;

function renderChart() {
  const pts = D.stocks.map(([t, p]) => ({ time: t, value: p }));
  chartValues = new Map(D.stocks.map(([t, , v]) => [t, v]));
  const c = { ink3: css("--ink-3"), rule: css("--rule"), line: css("--h-stocks") };
  if (!chart) {
    chart = LightweightCharts.createChart($("chart"), {
      autoSize: true,
      layout: { background: { type: "solid", color: "transparent" }, textColor: c.ink3, fontFamily: "Public Sans, system-ui, sans-serif", fontSize: 12, attributionLogo: false },
      grid: { vertLines: { visible: false }, horzLines: { color: c.rule } },
      rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.08, bottom: 0.06 } },
      timeScale: { borderVisible: false, timeVisible: true, secondsVisible: false, minBarSpacing: 0.05 },
      crosshair: { mode: LightweightCharts.CrosshairMode.Magnet },
      localization: { priceFormatter: (v) => num(v), locale: "en-GB" },
      handleScale: { axisPressedMouseMove: false },
    });
    series = chart.addBaselineSeries({
      baseValue: { type: "price", price: 0 },
      lineWidth: 2, priceLineVisible: false, lastValueVisible: false,
    });
  }
  series.setData(pts);
  if (!chartLegendBound) {
    chartLegendBound = true;
    const last = () => D.stocks[D.stocks.length - 1];
    const legend = $("chart-legend");
    show = (time, profit) => {
      const when = wallFmt.format(new Date(time * 1000));
      legend.replaceChildren(
        el("div", "l-profit", signed(profit)),
        el("div", "l-meta", `value ${money(chartValues.get(time) ?? 0, 0)} · ${when}`),
      );
    };
    chart.subscribeCrosshairMove((p) => {
      const d = p.time && p.seriesData.get(series);
      d ? show(p.time, d.value) : show(last()[0], last()[1]);
    });
    segmented($("range"), RANGES, state.range, (days) => { state.range = days; setRange(); });
  }
  // The chart parses its own colours: hex + alpha → rgba().
  const fill = (hex, a) => {
    const n = parseInt(hex.slice(1), 16);
    return `rgba(${n >> 16 & 255}, ${n >> 8 & 255}, ${n & 255}, ${a / 100})`;
  };
  series.applyOptions({
    topLineColor: c.line, topFillColor1: fill(c.line, 26), topFillColor2: fill(c.line, 2),
    bottomLineColor: c.ink3, bottomFillColor1: fill(c.ink3, 2), bottomFillColor2: fill(c.ink3, 22),
  });
  // New formatter object each render so the axis redraws when amounts are hidden.
  chart.applyOptions({
    layout: { textColor: c.ink3 }, grid: { horzLines: { color: c.rule } },
    localization: { priceFormatter: (v) => num(v), locale: "en-GB" },
  });
  const [t, p] = D.stocks[D.stocks.length - 1];
  show(t, p);
  setRange();
}

function setRange() {
  const last = D.stocks[D.stocks.length - 1][0];
  if (state.range) chart.timeScale().setVisibleRange({ from: last - state.range * 86400, to: last });
  else chart.timeScale().fitContent();
}

// --- Spending -----------------------------------------------------------------

function renderSpending() {
  const months = D.spending.months;
  const m = months[state.month], cmp = m.compare;
  $("month-name").textContent = monthFmt.format(monthDate(m.month));
  $("month-prev").disabled = state.month >= months.length - 1;
  $("month-next").disabled = state.month === 0;

  // The running month is compared with last month up to the same day.
  const cmpName = monthName.format(monthDate(cmp.month));
  const cmpLabel = cmp.to_day ? `${cmpName} 1–${cmp.to_day}` : cmpName;
  $("spent").replaceChildren(num(m.spent), " ", el("span", "cur", "zł spent"));
  // Savings rate = what's left of the month's income after its spending.
  const rate = m.income > 0 ? (m.income - m.spent) / m.income * 100 : null;
  $("spent-sub").textContent = `Income ${money(m.income, 0)} · ${rate === null ? "no income yet" : `saved ${rate < 0 ? "−" : ""}${NF0.format(Math.abs(rate))}%`}`;

  const cats = Object.entries(m.categories);
  const prevCats = cmp.categories;
  const max = Math.max(...cats.map(([, v]) => v), ...cats.map(([k]) => prevCats[k] || 0), 1);
  const list = $("cats");
  list.replaceChildren();
  for (const [cat, amount] of cats) {
    const li = el("li");
    const btn = el("button", "cat-row");
    btn.type = "button";
    btn.setAttribute("aria-expanded", String(state.openCat === cat));
    const track = el("span", "cat-track");
    const bar = el("span", "cat-bar");
    bar.style.width = `${amount / max * 100}%`;
    bar.style.background = catColor(cat);
    track.append(bar);
    const before = prevCats[cat];
    if (before) {
      const tick = el("span", "cat-prev");
      tick.style.left = `calc(${before / max * 100}% - 1px)`;
      tick.title = `${cmpLabel}: ${money(before, 0)}`;
      track.append(tick);
    }
    btn.append(el("span", "cat-name", cat), track, el("span", "cat-amt", money(amount, 0)));
    btn.addEventListener("click", () => {
      state.openCat = state.openCat === cat ? null : cat;
      renderSpending();
    });
    li.append(btn);
    if (state.openCat === cat) {
      const box = el("div", "cat-tx");
      if (before) box.append(el("p", "cat-cmp", `${cmpLabel}: ${money(before, 0)}`));
      const ul = el("ul", "tx-list");
      D.transactions
        .filter((t) => t.category === cat && t.date.startsWith(m.month) && t.amount < 0)
        .forEach((t) => ul.append(txItem(t, false)));
      box.append(ul);
      li.append(box);
    }
    list.append(li);
  }
  if (!cats.length) list.append(el("li", "hint", "No spending recorded this month."));
  $("cats-hint").textContent = cats.length ? `The tick is ${cmpLabel}. Tap a category for its transactions.` : "";
}

// --- Transactions -------------------------------------------------------------

function txItem(t, withCategory = true) {
  const li = el("li");
  const d = dayFmt.format(day(t.date));
  const r = row("", t.who || t.title || "—", signed(t.amount), withCategory ? `${d} · ` : d);
  if (withCategory) {
    const dot = el("i", "cat-dot");
    dot.style.background = catColor(t.category);
    r.querySelector(".r-meta").append(dot, t.category);
  }
  li.append(r);
  return li;
}

function renderRecent() {
  $("recent").replaceChildren(...D.transactions.slice(0, state.recent).map((t) => txItem(t)));
  $("recent-more").hidden = state.recent >= D.transactions.length;
}

function renderUncategorised() {
  const u = D.uncategorized;
  const total = u.reduce((s, x) => s + x.total, 0);
  $("uncat-summary").textContent = u.length
    ? `${u.length} merchants, ${money(total, 0)} without a category`
    : "Everything is categorised";
  $("uncat").replaceChildren(...u.map((x) => {
    const li = el("li");
    li.append(row("", x.who, money(x.total), `${x.count} transaction${x.count === 1 ? "" : "s"}`));
    return li;
  }));
}

// --- Freshness ------------------------------------------------------------------

function renderFreshness() {
  const f = D.freshness;
  const now = Date.now();
  const age = (iso) => (now - new Date(iso)) / 36e5;
  const item = (text, staleAfterHours, iso) => {
    const s = el("span", "", text);
    if (iso && age(iso) > staleAfterHours) {
      s.classList.add("stale");
      s.title = "Older than expected — the job may have failed.";
    }
    return s;
  };
  const items = [
    item(`Prices ${timeFmt.format(new Date(f.stocks))}`, 96, f.stocks),
    item(`Bank data ${timeFmt.format(new Date(f.banks))}`, 50, f.banks),
    item(`Built ${timeFmt.format(new Date(D.generated_at))}`, 26, D.generated_at),
  ];
  $("fresh").replaceChildren(...items);
}

// --- Boot -----------------------------------------------------------------------

function renderAll() {
  renderBalance();
  renderChart();
  renderSpending();
  renderRecent();
  renderUncategorised();
  renderFreshness();
}

async function load() {
  const res = await fetch("dashboard.json", { cache: "no-cache" });
  if (!res.ok) throw new Error(`dashboard.json: HTTP ${res.status}`);
  return res.json();
}

function showError(err) {
  const main = $("main");
  const box = el("section", "error");
  box.append(el("p", "label", "Couldn't load the data"),
    el("p", "", `${err.message}. The dashboard job writes dashboard.json; run it with: docker compose run --rm finance-jobs run-dashboard`));
  main.replaceChildren(box);
  main.setAttribute("aria-busy", "false");
}

// --- Hide amounts (to show the page to someone) --------------------------------

const HIDE_KEY = "finanse.hideAmounts";
function setHidden(on, save) {
  state.hidden = on;
  document.body.classList.toggle("hide-amounts", on);
  const b = $("hide");
  b.setAttribute("aria-pressed", String(on));
  b.setAttribute("aria-label", on ? "Show amounts" : "Hide amounts");
  b.title = on ? "Show amounts" : "Hide amounts";
  if (save) {
    try { localStorage.setItem(HIDE_KEY, on ? "1" : "0"); } catch { /* private window: per-visit only */ }
  }
  if (D) renderAll();
}
try { state.hidden = localStorage.getItem(HIDE_KEY) === "1"; } catch { /* default: shown */ }
setHidden(state.hidden, false);
$("hide").addEventListener("click", () => setHidden(!state.hidden, true));

let loadedAt = 0;
async function refresh(first) {
  try {
    D = await load();
    loadedAt = Date.now();
    renderAll();
    $("main").setAttribute("aria-busy", "false");
  } catch (err) {
    if (first) showError(err);
  }
}

$("month-prev").addEventListener("click", () => { state.month++; state.openCat = null; renderSpending(); });
$("month-next").addEventListener("click", () => { state.month--; state.openCat = null; renderSpending(); });
$("recent-more").addEventListener("click", () => { state.recent += RECENT_STEP * 2; renderRecent(); });
// Re-theme the chart when the OS flips light/dark.
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => D && renderChart());
// Coming back to the tab after a while: pick up whatever the jobs wrote.
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && Date.now() - loadedAt > 5 * 60e3) refresh(false);
});
refresh(true);
