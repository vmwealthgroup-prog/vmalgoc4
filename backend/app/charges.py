"""Indian retail trading cost model for paper trading and realistic P&L: brokerage, STT, exchange transaction charges, SEBI fee, stamp duty, GST.
DEFAULTS ARE APPROXIMATE (modelled on a typical discount-broker schedule) and Indian rates change often. Check your broker's brokerage calculator and
override any value with CHARGES_JSON, e.g. CHARGES_JSON='{"stt_options_sell_pct": 0.15}'. Original implementation; the idea is from public reference bots."""
import json
from dataclasses import dataclass, fields, replace
from .config import get_settings


@dataclass(frozen=True)
class Rates:
    brokerage_pct: float = 0.03          # % of turnover, capped at brokerage_flat per order (intraday, futures, options)
    brokerage_flat: float = 20.0
    delivery_brokerage: float = 0.0
    stt_intraday_sell_pct: float = 0.025
    stt_delivery_pct: float = 0.1        # both sides
    stt_futures_sell_pct: float = 0.02
    stt_options_sell_pct: float = 0.1    # on premium, sell side
    txn_equity_pct: float = 0.00297
    txn_futures_pct: float = 0.00183
    txn_options_pct: float = 0.03503     # on premium
    sebi_pct: float = 0.0001
    stamp_intraday_pct: float = 0.003    # buy side
    stamp_delivery_pct: float = 0.015
    stamp_futures_pct: float = 0.002
    stamp_options_pct: float = 0.003
    gst_pct: float = 18.0                # on brokerage + transaction charges + SEBI fee


def get_rates() -> Rates:
    raw = get_settings().charges_json.strip()
    if not raw:
        return Rates()
    over = json.loads(raw); known = {f.name for f in fields(Rates)}
    bad = set(over) - known
    if bad:
        raise ValueError(f"unknown charge keys: {sorted(bad)}")
    return replace(Rates(), **{k: float(v) for k, v in over.items()})


def instrument(exchange: str, symbol: str) -> str:
    ex, sym = exchange.upper(), symbol.upper()
    if ex in ("NFO", "BFO"):
        return "futures" if sym.endswith("FUT") else "options" if sym.endswith(("CE", "PE")) else "futures"
    if ex in ("NSE", "BSE"):
        return "equity"
    return "other"          # MCX / CRYPTO: not modelled, charges are 0


def calc(exchange, symbol, side, qty, price, product="MIS", rates: Rates | None = None) -> dict:
    r, kind, side = rates or get_rates(), instrument(exchange, symbol), side.upper()
    turnover = abs(qty) * price
    if kind == "other" or turnover <= 0:
        return {"total": 0.0, "instrument": kind, "turnover": round(turnover, 2)}
    delivery = kind == "equity" and product.upper() == "CNC"
    brokerage = r.delivery_brokerage if delivery else min(r.brokerage_flat, r.brokerage_pct / 100 * turnover)
    if kind == "equity":
        stt = r.stt_delivery_pct / 100 * turnover if delivery else (r.stt_intraday_sell_pct / 100 * turnover if side == "SELL" else 0.0)
        txn, stamp = r.txn_equity_pct / 100 * turnover, (r.stamp_delivery_pct if delivery else r.stamp_intraday_pct) / 100 * turnover * (side == "BUY")
    elif kind == "futures":
        stt = r.stt_futures_sell_pct / 100 * turnover * (side == "SELL"); txn = r.txn_futures_pct / 100 * turnover; stamp = r.stamp_futures_pct / 100 * turnover * (side == "BUY")
    else:
        stt = r.stt_options_sell_pct / 100 * turnover * (side == "SELL"); txn = r.txn_options_pct / 100 * turnover; stamp = r.stamp_options_pct / 100 * turnover * (side == "BUY")
    sebi = r.sebi_pct / 100 * turnover; gst = r.gst_pct / 100 * (brokerage + txn + sebi)
    parts = {"brokerage": brokerage, "stt": stt, "exchange_txn": txn, "sebi": sebi, "stamp_duty": stamp, "gst": gst}
    return {"total": round(sum(parts.values()), 2), "instrument": kind, "turnover": round(turnover, 2), **{k: round(v, 2) for k, v in parts.items()}}
