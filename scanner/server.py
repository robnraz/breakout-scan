#!/usr/bin/env python3
"""Web scanner for two classical breakout patterns.

Uses BennyThadikaran/stock-pattern (GPL-3.0) for the triangle test and
for swing pivots. Daily prices come from Yahoo Finance. The process
listens on 0.0.0.0:8080 so the preview can show it.
"""

from __future__ import annotations

import json
import threading
import time
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd
import yfinance as yf

from detect import _weekly, prepare, scan_frame

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
LAST = DATA / "last.json"

US = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO",
    "JPM", "V", "MA", "XOM", "UNH", "JNJ", "LLY", "COST", "WMT", "PG",
    "HD", "BAC", "KO", "PEP", "ABBV", "CRM", "ORCL", "AMD", "NFLX",
    "DIS", "CSCO", "CAT", "BA", "GE", "HON", "IBM", "GS", "MS", "NKE",
    "MCD", "AXP", "CVX", "MRK", "ABT", "WFC", "LIN", "ACN", "QCOM",
    "TXN", "AMAT", "INTU", "AMGN",
]

EUROPE = [
    "ASML.AS", "SAP.DE", "MC.PA", "OR.PA", "AIR.PA", "SAN.PA", "TTE.PA",
    "SU.PA", "AI.PA", "BNP.PA", "DG.PA", "KER.PA", "RMS.PA", "SAF.PA",
    "SIE.DE", "ALV.DE", "DTE.DE", "BMW.DE", "MBG.DE", "VOW3.DE", "MUV2.DE",
    "IFX.DE", "ADS.DE", "BAS.DE", "BAYN.DE", "NESN.SW", "NOVN.SW", "ROG.SW",
    "NOVO-B.CO", "SHEL.L", "AZN.L", "HSBA.L", "BP.L", "ULVR.L", "RIO.L",
    "GLEN.L", "REL.L",
]

CORE = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "JPM", "XOM", "CAT", "GE",
    "AMD", "WMT", "TSLA", "AVGO", "WDC", "HOOD", "TSM", "ASML", "ASML.AS",
    "SAP.DE", "ULVR.L", "TTE.PA", "BP.L", "MC.PA", "AIR.PA", "NESN.SW",
    "SHEL.L", "AZN.L", "SIE.DE", "NOVO-B.CO",
]

# Every front-month contract Yahoo actually publishes. Dated expiries are
# left out: they do not have a multi-year history to scan.
FUTURES = (
    "ES=F NQ=F YM=F RTY=F NKD=F MES=F MNQ=F MYM=F M2K=F EMD=F NIY=F "
    "BTC=F ETH=F MBT=F MET=F "
    "6E=F 6J=F 6B=F 6A=F 6C=F 6S=F 6N=F 6M=F M6E=F M6A=F M6B=F "
    "ZB=F ZN=F ZF=F ZT=F UB=F TN=F SR3=F "
    "GC=F SI=F HG=F PL=F PA=F MGC=F SIL=F ALI=F "
    "CL=F BZ=F NG=F HO=F RB=F MCL=F "
    "ZC=F ZW=F ZS=F ZM=F ZL=F ZO=F ZR=F KE=F "
    "LE=F HE=F GF=F DC=F "
    "KC=F SB=F CC=F CT=F OJ=F LBR=F"
).split()


def _us_all() -> list[str]:
    data = Path(__file__).resolve().parent / "data"
    blobs = []
    single = data / "us.txt"
    if single.exists():
        blobs.append(single.read_text())
    parts = data / "parts"
    if parts.is_dir():
        for path in sorted(parts.glob("*.txt")):
            blobs.append(path.read_text())
    rows = []
    for blob in blobs:
        rows.extend(blob.splitlines())
    if not rows:
        return list(US)
    out = []
    seen = set()
    for row in rows:
        sym = row.strip().upper()
        if sym and not sym.startswith("#") and sym not in seen:
            seen.add(sym)
            out.append(sym)
    return out or list(US)


US_ALL = _us_all()

_LIST_SETS = {
    "core": set(CORE),
    "us": set(US),
    "europe": set(EUROPE),
    "futures": set(FUTURES),
}


def groups_for(sym: str, label: str) -> list[str]:
    found = [name for name, symbols in _LIST_SETS.items() if sym in symbols]
    if label == "all":
        found.append("all")
    return found or [label]

LISTS = {
    "core": CORE,
    "us": US,
    "all": US_ALL,
    "europe": EUROPE,
    "both": list(dict.fromkeys(US + EUROPE)),
    "futures": FUTURES,
}

state = {
    "running": False,
    "phase": "Idle",
    "done": 0,
    "total": 0,
    "error": None,
    "updated": None,
    "list": None,
    "hits": [],
    "bars": {},
}
lock = threading.Lock()


def _bars(df: pd.DataFrame, limit: int = 200) -> list[list]:
    rows = []
    for ts, row in df.tail(limit).iterrows():
        rows.append(
            [
                pd.Timestamp(ts).strftime("%Y-%m-%d"),
                round(float(row.Open), 4),
                round(float(row.High), 4),
                round(float(row.Low), 4),
                round(float(row.Close), 4),
            ]
        )
    return rows


def _frame(data: pd.DataFrame, sym: str) -> pd.DataFrame | None:
    try:
        if isinstance(data.columns, pd.MultiIndex):
            sub = pd.DataFrame(
                {
                    "Open": data["Open"][sym],
                    "High": data["High"][sym],
                    "Low": data["Low"][sym],
                    "Close": data["Close"][sym],
                    "Volume": data["Volume"][sym],
                }
            )
        else:
            sub = data.rename(columns=str.title)[["Open", "High", "Low", "Close", "Volume"]]
        return sub.dropna()
    except Exception:
        return None


def _json_hit(hit: dict) -> dict:
    out = dict(hit)
    for key in ("start", "end"):
        if key in out:
            out[key] = pd.Timestamp(out[key]).strftime("%Y-%m-%d")
    return out


def _sort_hits(hits: list[dict]) -> list[dict]:
    def key(hit):
        triangle = 0 if hit["pattern"] == "triangle" else 1
        touches = -(hit.get("hits") or 0)
        return (triangle, touches, hit["symbol"])

    return sorted(hits, key=key)


def run_scan(symbols: list[str], label: str, keep: bool = False) -> None:
    prior_hits: list[dict] = []
    prior_bars: dict = {}
    if keep and LAST.exists():
        try:
            saved = json.loads(LAST.read_text())
            fresh = set(symbols)
            prior_hits = [hit for hit in saved.get("hits") or [] if hit.get("symbol") not in fresh]
            prior_bars = {
                key: value
                for key, value in (saved.get("bars") or {}).items()
                if key.split("|", 1)[0] not in fresh
            }
        except Exception:
            prior_hits, prior_bars = [], {}
    try:
        with lock:
            state.update(
                running=True,
                phase="Downloading daily prices",
                done=0,
                total=len(symbols),
                error=None,
                list=label,
                hits=list(prior_hits),
                bars=dict(prior_bars),
            )
        data = None
        hits = list(prior_hits)
        bars = dict(prior_bars)
        batch = 25
        for start in range(0, len(symbols), batch):
            chunk = symbols[start : start + batch]
            with lock:
                state["phase"] = "Downloading daily prices"
                state["done"] = start
            try:
                data = yf.download(
                    chunk,
                    period="5y",
                    interval="1d",
                    auto_adjust=True,
                    progress=False,
                    threads=True,
                    group_by="column",
                )
            except Exception:
                data = None
            with lock:
                state["phase"] = "Scanning daily and weekly"
            for offset, sym in enumerate(chunk, start=1):
                frame = _frame(data, sym) if data is not None else None
                found = []
                if frame is not None and len(frame) >= 80:
                    found = scan_frame(sym, frame)
                if found:
                    daily = prepare(frame)
                    last = float(frame.Close.iloc[-1])
                    prev = float(frame.Close.iloc[-2])
                    change = (last - prev) / prev * 100 if prev else 0.0
                    if daily is not None and any(hit.get("tf") != "W" for hit in found):
                        bars[f"{sym}|D"] = _bars(daily, 520)
                    if any(hit.get("tf") == "W" for hit in found) and daily is not None:
                        weekly = prepare(_weekly(daily))
                        if weekly is not None:
                            bars[f"{sym}|W"] = _bars(weekly, 110)
                    for hit in found:
                        hit["last"] = round(last, 4)
                        hit["change"] = round(change, 2)
                        hit["label"] = sym.split("=")[0] if "=" in sym else sym
                        hit["key"] = f"{sym}|{hit.get('tf', 'D')}"
                        hit["groups"] = groups_for(sym, label)
                        hits.append(_json_hit(hit))
                with lock:
                    state["done"] = start + offset
                    state["hits"] = _sort_hits(hits)
                    state["bars"] = bars
            time.sleep(0.25)
        updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        with lock:
            state["running"] = False
            state["phase"] = "Done"
            state["updated"] = updated
            snapshot = {
                "updated": updated,
                "list": label,
                "hits": state["hits"],
                "bars": state["bars"],
            }
        LAST.write_text(json.dumps(snapshot))
    except Exception as exc:
        traceback.print_exc()
        with lock:
            state["running"] = False
            state["phase"] = "Failed"
            state["error"] = str(exc)


def start_scan(symbols: list[str], label: str) -> bool:
    with lock:
        if state["running"]:
            return False
        state["running"] = True
    threading.Thread(target=run_scan, args=(symbols, label), daemon=True).start()
    return True


def load_last() -> None:
    if not LAST.exists():
        return
    try:
        saved = json.loads(LAST.read_text())
    except Exception:
        return
    with lock:
        if state["running"]:
            return
        state["hits"] = saved.get("hits") or []
        state["bars"] = saved.get("bars") or {}
        state["updated"] = saved.get("updated")
        state["list"] = saved.get("list")
        state["phase"] = "Done"
        state["done"] = len(LISTS.get(saved.get("list") or "", [])) or len({h["symbol"] for h in state["hits"]})
        state["total"] = state["done"]


def snapshot() -> dict:
    with lock:
        return {
            "app": "pattern-scan",
            "running": state["running"],
            "phase": state["phase"],
            "done": state["done"],
            "total": state["total"],
            "error": state["error"],
            "updated": state["updated"],
            "list": state["list"],
            "hits": state["hits"],
            "bars": state["bars"],
            "live": True,
        }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/health":
            body = json.dumps({"app": "pattern-scan", "ok": True}).encode()
            return self._send(200, body, "application/json")
        if path == "/api/status":
            body = json.dumps(snapshot()).encode()
            return self._send(200, body, "application/json")
        if path == "/api/scan":
            query = parse_qs(parsed.query)
            label = (query.get("list") or ["core"])[0]
            extra = (query.get("symbols") or [""])[0]
            symbols = list(LISTS.get(label, CORE))
            for raw in extra.replace(";", ",").split(","):
                sym = raw.strip().upper()
                if sym and sym not in symbols:
                    symbols.append(sym)
            if not symbols:
                return self._send(400, b'{"error":"no symbols"}', "application/json")
            started = start_scan(symbols, label if not extra.strip() else f"{label}+custom")
            body = json.dumps({**snapshot(), "started": started}).encode()
            return self._send(200, body, "application/json")

        rel = "index.html" if path == "/" else path.lstrip("/")
        file_path = (STATIC / rel).resolve()
        if not str(file_path).startswith(str(STATIC.resolve())) or not file_path.is_file():
            return self._send(404, b"Not found", "text/plain; charset=utf-8")
        ext = file_path.suffix.lower()
        types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".mjs": "text/javascript; charset=utf-8",
            ".svg": "image/svg+xml",
            ".txt": "text/plain; charset=utf-8",
        }
        return self._send(200, file_path.read_bytes(), types.get(ext, "application/octet-stream"))


def main() -> None:
    load_last()
    if not state["hits"]:
        start_scan(CORE, "core")
    server = ThreadingHTTPServer(("0.0.0.0", 8080), Handler)
    print("Pattern scan at http://0.0.0.0:8080", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
