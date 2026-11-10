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
    {"key": "ema_cross", "name": "EMA 9/21 crossover", "spec": {
        "entry": {"all": [{"left": {"ind": "ema", "period": 9}, "op": "crosses_above", "right": {"ind": "ema", "period": 21}}]},
        "exit": {"all": [{"left": {"ind": "ema", "period": 9}, "op": "crosses_below", "right": {"ind": "ema", "period": 21}}]}}},
    {"key": "rsi_reversion", "name": "RSI mean reversion", "spec": {
        "entry": {"all": [{"left": {"ind": "rsi", "period": 14}, "op": "<", "right": {"value": 30}}]},
        "exit": {"all": [{"left": {"ind": "rsi", "period": 14}, "op": ">", "right": {"value": 55}}]}}},
    {"key": "donchian", "name": "20-bar breakout with stop", "spec": {
        "entry": {"all": [{"left": {"ind": "close"}, "op": ">", "right": {"ind": "hh", "period": 20}}]},
        "exit": {"all": [{"left": {"ind": "close"}, "op": "<", "right": {"ind": "ll", "period": 10}}]},
        "risk": {"stop_pct": 2}}},
]
