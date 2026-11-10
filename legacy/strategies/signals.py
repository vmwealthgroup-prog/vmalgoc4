"""Pure signal functions shared by the backtester and the live runner.
Each takes an OHLC DataFrame (columns: open, high, low, close; datetime index)
and returns a Series of target positions: +1 long, -1 short, 0 flat."""
import pandas as pd


def ema_crossover(df, fast=9, slow=21):
    f = df["close"].ewm(span=fast, adjust=False).mean()
    s = df["close"].ewm(span=slow, adjust=False).mean()
    return (f > s).astype(int)


def rsi_mean_reversion(df, period=14, buy_below=30, exit_above=55):
    d = df["close"].diff()
    gain = d.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rsi = 100 - 100 / (1 + gain / loss.replace(0, 1e-12))
    state, out = 0, []
    for v in rsi:
        if state == 0 and v < buy_below:
            state = 1
        elif state == 1 and v > exit_above:
            state = 0
        out.append(state)
    return pd.Series(out, index=df.index)


def opening_range_breakout(df, range_bars=3):
    """Intraday: first `range_bars` bars set the range; trade the first break; flat at day end."""
    out = pd.Series(0, index=df.index, dtype=int)
    for _, day in df.groupby(df.index.date):
        if len(day) <= range_bars:
            continue
        hi, lo = day["high"].iloc[:range_bars].max(), day["low"].iloc[:range_bars].min()
        pos, vals = 0, []
        for i, c in enumerate(day["close"]):
            if i >= range_bars and pos == 0:
                pos = 1 if c > hi else -1 if c < lo else 0
            vals.append(pos)
        vals[-1] = 0
        out.loc[day.index] = vals
    return out


REGISTRY = {
    "ema_crossover": ema_crossover,
    "rsi_mean_reversion": rsi_mean_reversion,
    "opening_range_breakout": opening_range_breakout,
}
