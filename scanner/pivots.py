"""Swing pivots and the triangle test from BennyThadikaran/stock-pattern (GPL-3.0)."""

from typing import Optional

import pandas as pd


def is_triangle(a: float, b: float, c: float, d: float, e: float, f: float, avgBarLength: float) -> Optional[str]:
    if abs(a - c) <= avgBarLength and abs(c - e) <= avgBarLength and b < d < f < e:
        return "Ascending"
    if abs(b - d) <= avgBarLength and a > c > e > f and f >= d:
        return "Descending"
    if a > c > e and b < d < f and e > f:
        return "Symmetric"
    return None


def get_max_min(df: pd.DataFrame, barsLeft=6, barsRight=6, pivot_type="both") -> pd.DataFrame:
    window = barsLeft + 1 + barsRight
    local_max_dt = []
    local_min_dt = []
    for win in df.rolling(window):
        if win.shape[0] < window:
            continue
        idx = win.index[barsLeft + 1]
        if win.High.idxmax() == idx:
            local_max_dt.append(idx)
        if win.Low.idxmin() == idx:
            local_min_dt.append(idx)
    maxima = pd.DataFrame(df.loc[local_max_dt, ["High", "Volume"]])
    maxima.columns = ["P", "V"]
    minima = pd.DataFrame(df.loc[local_min_dt, ["Low", "Volume"]])
    minima.columns = ["P", "V"]
    if pivot_type == "high":
        return maxima
    if pivot_type == "low":
        return minima
    return pd.concat([maxima, minima], axis=0).sort_index()
