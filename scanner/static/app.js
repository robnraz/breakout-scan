const { createChart, CandlestickSeries, LineSeries } = await import("./vendor/lightweight-charts.mjs").catch(
  () => import("https://cdn.jsdelivr.net/npm/lightweight-charts@5.3.0/dist/lightweight-charts.standalone.production.mjs"),
);

const listEl = document.getElementById("list");
const statusEl = document.getElementById("status");
const titleEl = document.getElementById("chart-title");
const subEl = document.getElementById("chart-sub");
const pxEl = document.getElementById("chart-px");
const detailEl = document.getElementById("detail");
const scanBtn = document.getElementById("scan");
const form = document.getElementById("controls");
const chartHost = document.getElementById("chart");

let snapshot = { hits: [], bars: {}, running: true, live: true };
let filter = "all";
let universe = document.querySelector('input[name="list"]:checked')?.value || "core";
let tf = "all";
let selected = null;
let drawn = null;
let chart;
let candle;
const lines = [];

const chartOptions = {
  autoSize: true,
  layout: {
    background: { color: "#1b1e16" },
    textColor: "#9a947f",
    fontFamily: '"IBM Plex Sans", sans-serif',
  },
  grid: {
    vertLines: { color: "#2a2e24" },
    horzLines: { color: "#2a2e24" },
  },
  rightPriceScale: { borderColor: "#34382c" },
  timeScale: { borderColor: "#34382c" },
  crosshair: { vertLine: { color: "#d6a441" }, horzLine: { color: "#d6a441" } },
};

function ensureChart() {
  if (chart) return;
  chart = createChart(chartHost, chartOptions);
  candle = chart.addSeries(CandlestickSeries, {
    upColor: "#8ea56a",
    downColor: "#c46a55",
    borderVisible: false,
    wickUpColor: "#8ea56a",
    wickDownColor: "#c46a55",
  });
}

function clearLines() {
  while (lines.length) chart.removeSeries(lines.pop());
}

function closeness(hit) {
  if (!hit.level || !hit.last) return 1;
  return Math.abs(hit.last - hit.level) / Math.abs(hit.last);
}

function betterHit(a, b) {
  if (a.pattern !== b.pattern) {
    if (a.pattern === "triangle") return true;
    if (b.pattern === "triangle") return false;
  }
  const gap = closeness(a) - closeness(b);
  if (Math.abs(gap) > 0.008) return gap < 0;
  if (tf === "all" && a.tf !== b.tf) return a.tf === "D";
  return (a.hits || 0) > (b.hits || 0);
}

function hitGroups(hit) {
  if (Array.isArray(hit.groups) && hit.groups.length) return hit.groups;
  if (hit.group) return [hit.group];
  return null;
}

function hasUniverse(name) {
  return (snapshot.hits || []).some((hit) => (hitGroups(hit) || []).includes(name));
}

function inUniverse(hit) {
  const groups = hitGroups(hit);
  if (!groups) return true;
  if (universe === "both") return groups.includes("us") || groups.includes("europe");
  return groups.includes(universe);
}

function visibleHits() {
  const rows = (snapshot.hits || []).filter((hit) => {
    if (!inUniverse(hit)) return false;
    const patternOk = filter === "all" || hit.pattern === filter;
    const tfOk = tf === "all" || hit.tf === tf;
    return patternOk && tfOk;
  });
  const best = new Map();
  const order = [];
  for (const hit of rows) {
    const prev = best.get(hit.symbol);
    if (!prev) {
      order.push(hit.symbol);
      best.set(hit.symbol, hit);
    } else if (betterHit(hit, prev)) {
      best.set(hit.symbol, hit);
    }
  }
  return order.map((symbol) => best.get(symbol));
}

function otherTimeframe(hit) {
  const other = hit.tf === "W" ? "D" : "W";
  return (snapshot.hits || []).some((row) => {
    if (row.symbol !== hit.symbol || row.tf !== other) return false;
    return filter === "all" || row.pattern === filter;
  });
}

function money(n) {
  if (n == null || Number.isNaN(n)) return "\u2014";
  const abs = Math.abs(n);
  const digits = abs >= 1000 ? 1 : abs >= 20 ? 2 : abs >= 2 ? 3 : abs >= 0.5 ? 4 : 5;
  return n.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function renderList() {
  const hits = visibleHits();
  listEl.replaceChildren();
  if (!hits.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = snapshot.running
      ? "Scanning. Hits show up as they are found."
      : "No hits in this filter.";
    listEl.append(empty);
    return;
  }
  if (!hits.some((hit) => hitKey(hit) === selected)) selected = hitKey(hits[0]);
  for (const hit of hits) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "hit" + (hitKey(hit) === selected ? " on" : "");
    btn.setAttribute("role", "option");
    const change = hit.change || 0;
    const left = document.createElement("span");
    left.className = "sym";
    left.textContent = hit.label || hit.symbol;
    const px = document.createElement("span");
    px.className = "px " + (change >= 0 ? "up" : "down");
    px.textContent = money(hit.last);
    const name = document.createElement("span");
    name.className = "name";
    const also = otherTimeframe(hit) ? (hit.tf === "D" ? " \u00b7 weekly too" : " \u00b7 daily too") : "";
    name.textContent = (hit.hits ? `${hit.name} \u00b7 ${hit.hits} hits` : hit.name) + also;
    const ch = document.createElement("span");
    ch.className = "px " + (change >= 0 ? "up" : "down");
    ch.textContent = `${change >= 0 ? "+" : ""}${change.toFixed(2)}%`;
    btn.append(left, px, name, ch);
    btn.addEventListener("click", () => {
      selected = hitKey(hit);
      renderList();
      renderChart();
    });
    listEl.append(btn);
  }
}

function hitKey(hit) {
  return `${hit.symbol}:${hit.tf || "D"}:${hit.pattern}:${hit.level ?? hit.name}`;
}

function renderChart() {
  const hit = visibleHits().find((row) => hitKey(row) === selected) || visibleHits()[0];
  if (!hit) {
    titleEl.textContent = snapshot.running ? "Scan in progress" : "Nothing matched";
    subEl.textContent = snapshot.running ? "" : "Try Futures, the wider stock list, or type a ticker.";
    pxEl.textContent = "";
    detailEl.textContent = "";
    return;
  }
  selected = hitKey(hit);
  const raw = (snapshot.bars && (snapshot.bars[hit.key] || snapshot.bars[`${hit.symbol}|${hit.tf || "D"}`])) || [];
  const bars = Array.isArray(raw[0])
    ? raw.map(([time, open, high, low, close]) => ({ time, open, high, low, close }))
    : raw;
  const token = `${hitKey(hit)}:${bars.length}`;
  titleEl.textContent = `${hit.label || hit.symbol} \u00b7 ${hit.name}`;
  const bits = [hit.side];
  if (hit.level != null) bits.push(`level ${money(hit.level)}`);
  if (hit.hits) bits.push(`${hit.hits} touches`);
  subEl.textContent = bits.join(" \u00b7 ");
  const change = hit.change || 0;
  pxEl.textContent = `${money(hit.last)}  ${change >= 0 ? "+" : ""}${change.toFixed(2)}%`;
  pxEl.className = "px " + (change >= 0 ? "up" : "down");
  const touches = hit.points ? Object.entries(hit.points).map(([k, v]) => `${k} ${v[0]}`).join(" \u00b7 ") : "";
  detailEl.textContent = touches;

  if (!bars.length) return;
  if (drawn === token) return;
  drawn = token;
  ensureChart();
  const absPx = Math.abs(hit.last || 0);
  const precision = absPx >= 1000 ? 1 : absPx >= 20 ? 2 : absPx >= 2 ? 3 : absPx >= 0.5 ? 4 : 5;
  candle.applyOptions({
    priceFormat: { type: "price", precision, minMove: precision === 1 ? 0.1 : precision === 2 ? 0.01 : 0.001 },
  });
  candle.setData(bars);
  clearLines();
  const colors = ["#d6a441", "#c8c2ae"];
  (hit.lines || []).forEach((line, i) => {
    const series = chart.addSeries(LineSeries, {
      color: colors[i % colors.length],
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });
    series.setData(line.points.map(([time, value]) => ({ time, value })));
    lines.push(series);
  });
  const start = hit.points && Object.values(hit.points)[0] ? Object.values(hit.points)[0][0] : hit.lines?.[0]?.points?.[0]?.[0];
  const year = hit.tf === "W" ? 52 : 252;
  let from = start ? bars.findIndex((bar) => bar.time >= start) : 0;
  if (from < 0) from = 0;
  from = Math.max(0, from - 10);
  if (bars.length - from < year) from = Math.max(0, bars.length - year);
  chart.timeScale().setVisibleLogicalRange({
    from,
    to: bars.length + 3,
  });
}

function renderStatus() {
  if (snapshot.error) {
    statusEl.textContent = snapshot.error;
    return;
  }
  if (snapshot.running) {
    const phase = snapshot.phase || "Scanning";
    const prog = snapshot.total ? ` ${snapshot.done || 0} of ${snapshot.total}` : "";
    statusEl.textContent = `${phase}${prog}.`;
    return;
  }
  const n = (snapshot.hits || []).length;
  const shown = visibleHits().length;
  const when = snapshot.updated ? ` Last scan ${snapshot.updated}.` : "";
  statusEl.textContent = `${shown} names${n > shown ? `, ${n} patterns` : ""}.${when}`;
}

async function loadSnapshot() {
  try {
    const res = await fetch("/api/status", { cache: "no-store" });
    if (!res.ok) throw new Error("no api");
    const data = await res.json();
    if (!data || !("hits" in data)) throw new Error("bad");
    data.live = true;
    return data;
  } catch {
    const res = await fetch("last.json", { cache: "no-store" });
    const data = await res.json();
    data.live = false;
    data.running = false;
    return data;
  }
}

async function refresh() {
  snapshot = await loadSnapshot();
  const live = snapshot.live !== false;
  scanBtn.hidden = !live;
  scanBtn.disabled = Boolean(snapshot.running);
  scanBtn.textContent = snapshot.running ? "Scanning" : "Scan";
  renderStatus();
  renderList();
  renderChart();
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (snapshot.live === false || snapshot.running) return;
  const data = new FormData(form);
  const list = data.get("list") || "core";
  const symbols = (data.get("symbols") || "").toString().trim();
  scanBtn.disabled = true;
  statusEl.textContent = "Starting scan.";
  await fetch(`/api/scan?list=${encodeURIComponent(list)}&symbols=${encodeURIComponent(symbols)}`);
  await refresh();
});

form.querySelectorAll('input[name="list"]').forEach((input) => {
  input.addEventListener("change", () => {
    universe = input.value;
    selected = null;
    drawn = null;
    const needed = universe === "both" ? ["us", "europe"] : [universe];
    const present = needed.some((name) => hasUniverse(name));
    const tagged = (snapshot.hits || []).some((hit) => hitGroups(hit));
    if (snapshot.live && !snapshot.running && (!tagged || !present)) {
      form.requestSubmit();
      return;
    }
    renderStatus();
    renderList();
    renderChart();
    if (!present) {
      statusEl.textContent = universe === "all"
        ? "The full US list publishes with the morning run."
        : "That list is not in this scan.";
    }
  });
});

document.querySelectorAll("[data-filter]").forEach((btn) => {
  btn.addEventListener("click", () => {
    filter = btn.dataset.filter;
    document.querySelectorAll("[data-filter]").forEach((el) => el.classList.toggle("on", el === btn));
    selected = null;
    drawn = null;
    renderStatus();
    renderList();
    renderChart();
  });
});

document.querySelectorAll("[data-tf]").forEach((btn) => {
  btn.addEventListener("click", () => {
    tf = btn.dataset.tf;
    document.querySelectorAll("[data-tf]").forEach((el) => el.classList.toggle("on", el === btn));
    selected = null;
    drawn = null;
    renderStatus();
    renderList();
    renderChart();
  });
});

await refresh();
setInterval(() => {
  if (snapshot.running || document.visibilityState === "visible") refresh().catch(() => {});
}, 1500);
