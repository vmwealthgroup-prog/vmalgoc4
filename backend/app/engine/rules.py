"""Strategy-builder rule engine. A strategy spec is JSON, so the UI can build it and the backtester, scanner and live runner
all evaluate the SAME rules.

Operand: {"ind": "close|open|high|low|volume|ema|sma|rsi|atr|hh|ll", "period": 14} or {"value": 30}
Condition: {"left": Operand, "op": ">|<|>=|<=|crosses_above|crosses_below", "right": Operand}
Group: {"all": [Condition...]} or {"any": [Condition...]}"""
import numpy as np
import pandas as pd

OPS = {">", "<", ">=", "<=", "crosses_above", "crosses_below"}
INDS = {"close", "open", "high", "low", "volume", "ema", "sma", "rsi", "atr", "hh", "ll"}


def indicator(df: pd.DataFrame, ind: str, period: int = 14) -> pd.Series:
    c = df["close"]
    if ind in ("close", "open", "high", "low"):
        return df[ind]
    if ind == "volume":
        return df["volume"] if "volume" in df else pd.Series(0.0, index=df.index)
    if ind == "ema":
        return c.ewm(span=period, adjust=False).mean()
    if ind == "sma":
        return c.rolling(period).mean()
    if ind == "rsi":
        d = c.diff()
        g = d.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
        l = (-d.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
        return 100 - 100 / (1 + g / l.replace(0, 1e-12))
    if ind == "atr":
        pc = c.shift(1)
        tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
        return tr.ewm(alpha=1 / period, adjust=False).mean()
    if ind == "hh":   # highest high of the PREVIOUS `period` bars (breakout level)
        return df["high"].rolling(period).max().shift(1)
    if ind == "ll":
        return df["low"].rolling(period).min().shift(1)
    raise ValueError(f"unknown indicator {ind}")


def _operand(df, o):
    if "value" in o:
        return pd.Series(float(o["value"]), index=df.index)
    return indicator(df, o["ind"], int(o.get("period", 14)))


def eval_condition(df, cond) -> pd.Series:
    a, b, op = _operand(df, cond["left"]), _operand(df, cond["right"]), cond["op"]
    if op == ">": r = a > b
    elif op == "<": r = a < b
    elif op == ">=": r = a >= b
    elif op == "<=": r = a <= b
    elif op == "crosses_above": r = (a > b) & (a.shift(1) <= b.shift(1))
    elif op == "crosses_below": r = (a < b) & (a.shift(1) >= b.shift(1))
    else: raise ValueError(f"unknown operator {op}")
    return r.fillna(False)


def eval_group(df, group) -> pd.Series:
    if not group:
        return pd.Series(False, index=df.index)
    key = "all" if "all" in group else "any"
    parts = [eval_condition(df, c) for c in group.get(key, [])]
    if not parts:
        return pd.Series(False, index=df.index)
    out = parts[0]
    for p in parts[1:]:
        out = (out & p) if key == "all" else (out | p)
    return out


def validate_group(group, where="rule"):
    if not isinstance(group, dict) or not ({"all", "any"} & set(group)):
        raise ValueError(f"{where}: needs an 'all' or 'any' list")
    for c in group.get("all", group.get("any", [])):
        if c.get("op") not in OPS:
            raise ValueError(f"{where}: bad operator {c.get('op')}")
        for side in ("left", "right"):
            o = c.get(side) or {}
            if "value" in o:
                float(o["value"])
            elif o.get("ind") not in INDS:
                raise ValueError(f"{where}: bad indicator {o.get('ind')}")
            elif not 1 <= int(o.get("period", 14)) <= 1000:
                raise ValueError(f"{where}: period out of range")


def validate_spec(spec: dict) -> dict:
    for k in ("symbol", "exchange", "interval"):
        if not spec.get(k):
            raise ValueError(f"spec.{k} is required")
    if spec.get("side", "long") not in ("long", "short"):
        raise ValueError("side must be long or short")
    validate_group(spec.get("entry"), "entry")
    if spec.get("exit"):
        validate_group(spec["exit"], "exit")
    r = spec.get("risk", {})
    for k in ("stop_pct", "take_pct", "risk_pct", "equity", "max_qty", "qty"):
        if k in r and float(r[k]) < 0:
            raise ValueError(f"risk.{k} must be >= 0")
    return spec


def positions(df: pd.DataFrame, spec: dict) -> pd.Series:
    """Target position series (+1 long, -1 short, 0 flat) decided at each bar's close. Trade on the NEXT bar."""
    sign = 1 if spec.get("side", "long") == "long" else -1
    entry = eval_group(df, spec["entry"]).values
    exit_ = eval_group(df, spec["exit"]).values if spec.get("exit") else np.zeros(len(df), bool)
    risk = spec.get("risk", {}); stop = float(risk.get("stop_pct", 0)) / 100; take = float(risk.get("take_pct", 0)) / 100
    close = df["close"].values; out = np.zeros(len(df), dtype=int); pos = 0; ep = 0.0
    for i in range(len(df)):
        if pos != 0:
            move = (close[i] / ep - 1) * pos
            if exit_[i] or (stop and move <= -stop) or (take and move >= take):
                pos = 0
        elif entry[i]:
            pos, ep = sign, close[i]
        out[i] = pos
    return pd.Series(out, index=df.index)


TEMPLATES = [
    {
        "key": "ema_cross", "name": "EMA 9/21 crossover", "category": "Trend", "origin": "Core systematic",
        "description": "A simple moving-average crossover baseline. Waits for the fast EMA to cross the slow EMA.",
        "research_note": "Baseline model; compare it against the more selective champion-inspired templates.",
        "spec": {
            "entry": {"all": [{"left": {"ind": "ema", "period": 9}, "op": "crosses_above", "right": {"ind": "ema", "period": 21}}]},
            "exit": {"all": [{"left": {"ind": "ema", "period": 9}, "op": "crosses_below", "right": {"ind": "ema", "period": 21}}]}
        }
    },
    {
        "key": "rsi_reversion", "name": "RSI mean reversion", "category": "Mean reversion", "origin": "Quant research",
        "description": "Looks for an oversold RSI recovery and exits as momentum normalises.",
        "research_note": "Long-only template. Mean-reversion systems can struggle in persistent downtrends; test regime filters.",
        "spec": {
            "entry": {"all": [{"left": {"ind": "rsi", "period": 14}, "op": "<", "right": {"value": 30}}]},
            "exit": {"all": [{"left": {"ind": "rsi", "period": 14}, "op": ">", "right": {"value": 55}}]}
        }
    },
    {
        "key": "donchian", "name": "20-bar breakout with stop", "category": "Breakout", "origin": "Trend following",
        "description": "Enters when the close breaks the prior 20-bar high and exits below the prior 10-bar low.",
        "research_note": "Prior-bar breakout levels avoid using the current candle in the breakout threshold.",
        "spec": {
            "entry": {"all": [{"left": {"ind": "close"}, "op": ">", "right": {"ind": "hh", "period": 20}}]},
            "exit": {"all": [{"left": {"ind": "close"}, "op": "<", "right": {"ind": "ll", "period": 10}}]},
            "risk": {"stop_pct": 2}
        }
    },
    {
        "key": "vm_momentum_pullback", "name": "VM Momentum Pullback", "category": "Swing momentum", "origin": "Inspired by Oliver Kell-style momentum principles",
        "description": "Trend alignment plus a pullback toward EMA 20, with RSI strength confirmation.",
        "research_note": "A rules-based research interpretation, not Oliver Kell's proprietary method. Volume confirmation is omitted until volume-average support is added to the rule engine.",
        "spec": {
            "symbol": "RELIANCE", "exchange": "NSE", "interval": "1d", "side": "long",
            "entry": {"all": [
                {"left": {"ind": "ema", "period": 20}, "op": ">", "right": {"ind": "ema", "period": 50}},
                {"left": {"ind": "close"}, "op": ">", "right": {"ind": "ema", "period": 200}},
                {"left": {"ind": "low"}, "op": "<=", "right": {"ind": "ema", "period": 20}},
                {"left": {"ind": "close"}, "op": ">", "right": {"ind": "ema", "period": 20}},
                {"left": {"ind": "rsi", "period": 14}, "op": ">=", "right": {"value": 55}},
                {"left": {"ind": "rsi", "period": 14}, "op": "<=", "right": {"value": 70}}
            ]},
            "exit": {"any": [
                {"left": {"ind": "close"}, "op": "<", "right": {"ind": "ema", "period": 20}},
                {"left": {"ind": "ema", "period": 20}, "op": "crosses_below", "right": {"ind": "ema", "period": 50}}
            ]},
            "risk": {"qty": 1, "stop_pct": 2, "take_pct": 4}
        }
    },
    {
        "key": "vm_breakout_volume", "name": "VM Breakout", "category": "Breakout", "origin": "Systematic price breakout",
        "description": "Prior 20-bar high breakout with medium- and long-term trend alignment.",
        "research_note": "The current rule engine does not yet support volume-SMA operands; this version intentionally does not claim volume confirmation.",
        "spec": {
            "symbol": "RELIANCE", "exchange": "NSE", "interval": "15m", "side": "long",
            "entry": {"all": [
                {"left": {"ind": "close"}, "op": ">", "right": {"ind": "hh", "period": 20}},
                {"left": {"ind": "ema", "period": 20}, "op": ">", "right": {"ind": "ema", "period": 50}},
                {"left": {"ind": "close"}, "op": ">", "right": {"ind": "ema", "period": 200}}
            ]},
            "exit": {"any": [
                {"left": {"ind": "close"}, "op": "<", "right": {"ind": "ema", "period": 20}},
                {"left": {"ind": "close"}, "op": "<", "right": {"ind": "ll", "period": 10}}
            ]},
            "risk": {"qty": 1, "stop_pct": 2, "take_pct": 4}
        }
    },
    {
        "key": "vm_intraday_pullback", "name": "VM Intraday Pullback", "category": "Intraday", "origin": "Momentum pullback research",
        "description": "Intraday trend filter with a pullback and bullish EMA reclaim trigger.",
        "research_note": "Use liquid symbols and realistic intraday costs. VWAP is not currently an available rule-engine indicator, so it is not represented as a condition.",
        "spec": {
            "symbol": "RELIANCE", "exchange": "NSE", "interval": "5m", "side": "long",
            "entry": {"all": [
                {"left": {"ind": "ema", "period": 10}, "op": ">", "right": {"ind": "ema", "period": 20}},
                {"left": {"ind": "low"}, "op": "<=", "right": {"ind": "ema", "period": 20}},
                {"left": {"ind": "close"}, "op": "crosses_above", "right": {"ind": "ema", "period": 10}},
                {"left": {"ind": "rsi", "period": 14}, "op": ">", "right": {"value": 50}}
            ]},
            "exit": {"all": [{"left": {"ind": "close"}, "op": "crosses_below", "right": {"ind": "ema", "period": 20}}]},
            "risk": {"qty": 1, "stop_pct": 1, "take_pct": 2, "square_off": "15:15"}
        }
    },
    {
        "key": "vm_quant_recovery", "name": "VM Quant Recovery", "category": "Quant research", "origin": "Inspired by systematic quantitative research",
        "description": "Oversold RSI recovery with a price-above-EMA-20 confirmation and predefined exits.",
        "research_note": "A transparent rule-based prototype, not a statistical-arbitrage model. Validate across symbols and market regimes before use.",
        "spec": {
            "symbol": "RELIANCE", "exchange": "NSE", "interval": "1d", "side": "long",
            "entry": {"all": [
                {"left": {"ind": "rsi", "period": 14}, "op": "crosses_above", "right": {"value": 30}},
                {"left": {"ind": "close"}, "op": ">", "right": {"ind": "ema", "period": 20}}
            ]},
            "exit": {"all": [{"left": {"ind": "rsi", "period": 14}, "op": ">", "right": {"value": 55}}]},
            "risk": {"qty": 1, "stop_pct": 1.5, "take_pct": 3}
        }
    },
    {
        "key": "vm_trend_filter", "name": "VM Trend", "category": "Trend following", "origin": "Multi-timeframe trend principles",
        "description": "Three-EMA trend stack with RSI confirmation; designed as a clean trend-following baseline.",
        "research_note": "ADX and SuperTrend are not yet supported by this rule engine. This template uses supported EMA/RSI conditions instead of silently approximating them.",
        "spec": {
            "symbol": "RELIANCE", "exchange": "NSE", "interval": "1h", "side": "long",
            "entry": {"all": [
                {"left": {"ind": "ema", "period": 20}, "op": ">", "right": {"ind": "ema", "period": 50}},
                {"left": {"ind": "ema", "period": 50}, "op": ">", "right": {"ind": "ema", "period": 200}},
                {"left": {"ind": "close"}, "op": ">", "right": {"ind": "ema", "period": 20}},
                {"left": {"ind": "rsi", "period": 14}, "op": ">", "right": {"value": 50}}
            ]},
            "exit": {"all": [{"left": {"ind": "ema", "period": 20}, "op": "crosses_below", "right": {"ind": "ema", "period": 50}}]},
            "risk": {"qty": 1, "stop_pct": 2, "take_pct": 4}
        }
    }
]
