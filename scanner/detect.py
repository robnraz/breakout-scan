"""Flat-side triangles and horizontal breakout levels.

Triangle shape is decided by BennyThadikaran/stock-pattern (GPL-3.0)
utils.is_triangle. Symmetric triangles are dropped. Only ascending and
descending triangles (one side horizontal) are kept, and only while price
is still inside them.

Horizontal levels use the same swing pivots. A level needs two touches and
price has to be back on it. A prior break that has come back to the line
still counts. A line through the middle of a range does not.
"""

from __future__ import annotations

import pandas as pd

import pivots as swing


def _num(value) -> float:
    if hasattr(value, "iloc"):
        value = value.iloc[0] if len(value) else value
    return float(value)


def _iso(ts) -> str:
    return pd.Timestamp(ts).strftime("%Y-%m-%d")


def prepare(df: pd.DataFrame) -> pd.DataFrame | None:
    if df is None or df.empty:
        return None
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = out.columns.get_level_values(0)
    needed = ["Open", "High", "Low", "Close", "Volume"]
    if not all(col in out.columns for col in needed):
        return None
    out = out[needed].apply(pd.to_numeric, errors="coerce").dropna()
    if out.index.has_duplicates:
        out = out.loc[~out.index.duplicated()]
    if not out.index.is_monotonic_increasing:
        out = out.sort_index()
    out.index = pd.DatetimeIndex(out.index).tz_localize(None)
    if len(out) < 80:
        return None
    return out


def _weekly(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.resample("W-FRI")
        .agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
        .dropna()
    )


def _extend(index, x1, y1, x2, y2, x_end) -> float:
    i1 = index.get_loc(x1)
    i2 = index.get_loc(x2)
    i_end = index.get_loc(x_end)
    if not isinstance(i1, int) or not isinstance(i2, int) or i2 == i1:
        return float(y2)
    slope = (y2 - y1) / (i2 - i1)
    return float(y1 + slope * (int(i_end) - i1))


def find_flat_triangles(df: pd.DataFrame, max_age: int = 40) -> dict | None:
    """Ascending or descending triangle with one horizontal side, still forming."""
    pivots = swing.get_max_min(df, barsLeft=5, barsRight=5, pivot_type="both")
    if pivots is None or len(pivots) < 5:
        return None

    highs = []
    lows = []
    for ts, price in zip(pivots.index, pivots["P"]):
        price = _num(price)
        bar_high = _num(df.at[ts, "High"])
        bar_low = _num(df.at[ts, "Low"])
        if abs(price - bar_high) <= abs(price - bar_low):
            highs.append((ts, price))
        else:
            lows.append((ts, price))

    if len(highs) < 3 or len(lows) < 2:
        return None

    f_idx = df.index[-1]
    f = _num(df.Close.iloc[-1])
    atr = float((df.High - df.Low).tail(14).median()) or 0.0
    best = None
    recent_cut = df.index[-120] if len(df) > 120 else df.index[0]

    for e_i, (e_idx, e) in enumerate(highs):
        if e_idx < recent_cut:
            continue
        for c_i in range(e_i - 1, -1, -1):
            c_idx, c = highs[c_i]
            for a_i in range(c_i - 1, -1, -1):
                a_idx, a = highs[a_i]
                span_days = (e_idx - a_idx).days
                if span_days < 30 or span_days > (500 if max_age > 40 else 200):
                    continue
                b_candidates = [(ts, p) for ts, p in lows if a_idx < ts < c_idx]
                d_candidates = [(ts, p) for ts, p in lows if c_idx < ts < e_idx]
                if not b_candidates or not d_candidates:
                    continue
                b_idx, b = min(b_candidates, key=lambda item: item[1])
                d_idx, d = min(d_candidates, key=lambda item: item[1])

                sl = df.loc[a_idx:e_idx]
                if len(sl) < 12:
                    continue
                avg_bar = float((sl["High"] - sl["Low"]).median()) or atr
                kind = swing.is_triangle(a, b, c, d, e, f, avg_bar)
                if kind not in ("Ascending", "Descending"):
                    continue
                if int(df.index.get_loc(f_idx)) - int(df.index.get_loc(e_idx)) > max_age:
                    continue

                flat_tol = max(min(avg_bar * 0.85, f * 0.012), f * 0.004)
                if kind == "Ascending":
                    flat_points = (a, c, e)
                    flat = float(pd.Series(flat_points).median())
                    if max(abs(p - flat) for p in flat_points) > flat_tol:
                        continue
                    if not (d > b and (d - b) >= flat_tol * 0.8):
                        continue
                    if not _still_inside(
                        df, "Ascending", flat, flat_tol, atr, f, f_idx,
                        a_idx, a, b_idx, b, c_idx, c, d_idx, d, e_idx,
                    ):
                        continue
                    y_end = _extend(df.index, b_idx, b, d_idx, d, f_idx)
                    lines = [
                        {"label": "Flat high", "points": [(_iso(a_idx), round(flat, 4)), (_iso(f_idx), round(flat, 4))]},
                        {"label": "Rising lows", "points": [(_iso(b_idx), round(b, 4)), (_iso(f_idx), round(y_end, 4))]},
                    ]
                else:
                    flat = (b + d) / 2
                    if abs(b - d) > flat_tol:
                        continue
                    if not (a > c > e and (a - e) >= flat_tol * 0.8):
                        continue
                    if not _still_inside(
                        df, "Descending", flat, flat_tol, atr, f, f_idx,
                        a_idx, a, b_idx, b, c_idx, c, d_idx, d, e_idx,
                    ):
                        continue
                    y_end = _extend(df.index, a_idx, a, c_idx, c, f_idx)
                    lines = [
                        {"label": "Falling highs", "points": [(_iso(a_idx), round(a, 4)), (_iso(f_idx), round(y_end, 4))]},
                        {"label": "Flat low", "points": [(_iso(b_idx), round(flat, 4)), (_iso(f_idx), round(flat, 4))]},
                    ]

                score = abs(f - flat) / max(atr, 1e-6) + span_days / 400
                hit = {
                    "pattern": "triangle",
                    "name": f"{kind} triangle",
                    "side": "Flat high" if kind == "Ascending" else "Flat low",
                    "score": score,
                    "level": round(flat, 4),
                    "start": a_idx,
                    "end": f_idx,
                    "lines": lines,
                    "points": {
                        "A": (_iso(a_idx), round(a, 4)),
                        "B": (_iso(b_idx), round(b, 4)),
                        "C": (_iso(c_idx), round(c, 4)),
                        "D": (_iso(d_idx), round(d, 4)),
                        "E": (_iso(e_idx), round(e, 4)),
                    },
                }
                if best is None or hit["score"] < best["score"]:
                    best = hit

    if best:
        best.pop("score", None)
    return best


def _still_inside(df, kind, flat, flat_tol, atr, f, f_idx, a_idx, a, b_idx, b, c_idx, c, d_idx, d, e_idx) -> bool:
    """Price never left the triangle, and the breakout has not already run."""
    noise = max(flat_tol * 0.35, atr * 0.3)
    window = df.loc[a_idx:]
    if window.empty:
        return False
    if kind == "Ascending":
        if float(window["High"].max()) > flat + flat_tol * 1.05:
            return False
        if float(window["Close"].max()) > flat + noise:
            return False
        for ts, row in df.loc[d_idx:].iterrows():
            support = _extend(df.index, b_idx, b, d_idx, d, ts)
            if float(row.Close) < support - noise:
                return False
        y_now = _extend(df.index, b_idx, b, d_idx, d, f_idx)
        if y_now >= flat:
            return False
        return y_now - noise <= f <= flat + noise
    if float(window["Low"].min()) < flat - flat_tol * 1.05:
        return False
    if float(window["Close"].min()) < flat - noise:
        return False
    for ts, row in df.loc[e_idx:].iterrows():
        ceiling = _extend(df.index, a_idx, a, c_idx, c, ts)
        if float(row.Close) > ceiling + noise:
            return False
    y_now = _extend(df.index, a_idx, a, c_idx, c, f_idx)
    if y_now <= flat:
        return False
    return flat - noise <= f <= y_now + noise


def _cluster(points: list[tuple], tol: float) -> list[dict]:
    groups: list[dict] = []
    for ts, price in sorted(points, key=lambda item: item[1]):
        placed = False
        for group in groups:
            prices = [p for _, p in group["pts"]] + [price]
            if max(prices) - min(prices) <= tol:
                group["pts"].append((ts, price))
                group["level"] = sum(prices) / len(prices)
                placed = True
                break
        if not placed:
            groups.append({"level": price, "pts": [(ts, price)]})
    return groups


def _unbroken(window: pd.DataFrame, level: float, role: str, weekly: bool) -> bool:
    """The line held. A day or two a little through it is fine.

    A close several percent through the line, or a string of closes on the
    wrong side, means price already went through and came back.
    """
    if window.empty or level <= 0:
        return False
    atr = float((window["High"] - window["Low"]).tail(14).median()) or level * 0.01
    poke = max(level * 0.012, atr * 0.35)
    hard = level * 0.03
    closes = window["Close"].astype(float)
    if role == "resistance":
        beyond = closes - level
        wick = window["High"].astype(float) - level
    else:
        beyond = level - closes
        wick = level - window["Low"].astype(float)
    if float(beyond.max()) > hard or float(wick.max()) > level * 0.045:
        return False
    max_run = 1 if weekly else 2
    max_total = 2 if weekly else 3
    run = 0
    worst = 0
    total = 0
    for value in beyond:
        if value > poke:
            run += 1
            total += 1
            worst = max(worst, run)
        else:
            run = 0
    return worst <= max_run and total <= max_total


def find_horizontal(df: pd.DataFrame, weekly: bool = False, min_hits: int = 2) -> list[dict]:
    """Horizontal the price is back on, daily or weekly."""
    left = 3 if weekly else 5
    right = 3 if weekly else 5
    pivots = swing.get_max_min(df, barsLeft=left, barsRight=right, pivot_type="both")
    if pivots is None or len(pivots) < 2:
        return []

    close = _num(df.Close.iloc[-1])
    if close <= 0:
        return []
    width = 0.045 if weekly else 0.04
    max_dist = 0.09 if weekly else 0.085
    tol = close * width
    recent = df.tail(16 if weekly else 30)
    live = df.tail(4 if weekly else 15)
    min_gap = 3 if weekly else 8

    highs = []
    lows = []
    for ts, price in zip(pivots.index, pivots["P"]):
        price = _num(price)
        if abs(price - _num(df.at[ts, "High"])) <= abs(price - _num(df.at[ts, "Low"])):
            highs.append((ts, price))
        else:
            lows.append((ts, price))

    found = []
    for kind, groups in (("high", _cluster(highs, tol)), ("low", _cluster(lows, tol))):
        series = live["High"] if kind == "high" else live["Low"]
        for group in groups:
            pts = group["pts"]
            level = float(group["level"])
            times = sorted(ts for ts, _ in pts)
            gap = int(df.index.get_loc(times[-1])) - int(df.index.get_loc(times[0]))
            tagged = any(abs(_num(v) - level) <= tol for v in series)
            hits = len(pts)
            if tagged and int(df.index.get_loc(df.index[-1])) - int(df.index.get_loc(times[-1])) > (1 if weekly else 3):
                hits += 1
            if hits < min_hits or (len(pts) < 2 and gap < min_gap and not tagged):
                continue
            if len(pts) >= 2 and gap < min_gap:
                continue
            if abs(close - level) / level > max_dist:
                continue
            window = df.loc[times[0] :]
            if kind == "low":
                away = (float(window["High"].max()) - level) / level
            else:
                away = (level - float(window["Low"].min())) / level
            if away < 0.05:
                continue
            inside = float(((recent["High"] >= level) & (recent["Low"] <= level)).mean())
            if inside > 0.22:
                continue
            above = float((recent["Close"] > level).mean())
            if kind == "high" and above >= 0.55 and tagged:
                label = "Testing support"
            elif kind == "low" and above <= 0.45 and tagged:
                label = "Testing resistance"
            elif kind == "low" and above >= 0.55:
                label = "Testing support"
            elif kind == "high" and above <= 0.45:
                label = "Testing resistance"
            else:
                continue
            role = "support" if label == "Testing support" else "resistance"
            if not _unbroken(window, level, role, weekly):
                continue
            # The latest push has to meet the line. A 2% gap is a line in the air.
            band = level * (0.018 if weekly else 0.015)
            if role == "resistance":
                extreme = float(df["High"].tail(4 if weekly else 15).max())
                if extreme < level - band:
                    continue
            else:
                extreme = float(df["Low"].tail(15 if not weekly else 4).min())
                if extreme > level + band:
                    continue
            found.append(
                {
                    "pattern": "horizontal",
                    "name": f"Horizontal · {label.lower()}",
                    "side": label,
                    "hits": hits,
                    "level": round(level, 4),
                    "start": times[0],
                    "end": df.index[-1],
                    "lines": [
                        {
                            "label": f"{hits} hits",
                            "points": [
                                (_iso(times[0]), round(level, 4)),
                                (_iso(df.index[-1]), round(level, 4)),
                            ],
                        }
                    ],
                    "points": {
                        chr(65 + i): (_iso(ts), round(price, 4))
                        for i, (ts, price) in enumerate(sorted(pts, key=lambda item: item[0])[:8])
                    },
                }
            )

    found.sort(key=lambda row: (abs(close - row["level"]) / close, -row["hits"]))
    kept = []
    seen = set()
    for row in found:
        if row["side"] in seen:
            continue
        seen.add(row["side"])
        kept.append(row)
    return kept[:2]


def _tag(hit: dict, tf: str) -> dict:
    hit = dict(hit)
    hit["tf"] = tf
    hit["name"] = f"{'Weekly' if tf == 'W' else 'Daily'} · {hit['name']}"
    return hit


def scan_frame(sym: str, df: pd.DataFrame) -> list[dict]:
    daily = prepare(df)
    if daily is None:
        return []
    hits = []
    try:
        triangle = find_flat_triangles(daily, max_age=40)
    except Exception:
        triangle = None
    if triangle:
        hits.append(_tag(triangle, "D"))
    try:
        for row in find_horizontal(daily, weekly=False):
            hits.append(_tag(row, "D"))
    except Exception:
        pass

    weekly = prepare(_weekly(daily))
    if weekly is not None:
        try:
            triangle_w = find_flat_triangles(weekly, max_age=20)
        except Exception:
            triangle_w = None
        if triangle_w:
            hits.append(_tag(triangle_w, "W"))
        try:
            for row in find_horizontal(weekly, weekly=True):
                hits.append(_tag(row, "W"))
        except Exception:
            pass

    for hit in hits:
        hit["symbol"] = sym
    return hits
