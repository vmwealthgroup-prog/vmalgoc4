from datetime import datetime, timezone
from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


def now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="user")          # user | admin
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class BrokerAccount(Base):
    __tablename__ = "broker_accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))                          # paper | openalgo
    label: Mapped[str] = mapped_column(String(80))
    broker_name: Mapped[str] = mapped_column(String(40), default="")       # informational: zerodha, angel, ...
    host: Mapped[str] = mapped_column(String(255), default="")
    api_key_enc: Mapped[str] = mapped_column(Text, default="")             # Fernet-encrypted
    live_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    paper_cash: Mapped[float] = mapped_column(Float, default=1_000_000.0)
    paper_charges: Mapped[float] = mapped_column(Float, default=0.0)       # cumulative simulated brokerage, taxes and fees
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PaperPosition(Base):
    __tablename__ = "paper_positions"
    __table_args__ = (UniqueConstraint("account_id", "symbol", "exchange"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("broker_accounts.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(40))
    exchange: Mapped[str] = mapped_column(String(20))
    qty: Mapped[float] = mapped_column(Float, default=0)
    avg_price: Mapped[float] = mapped_column(Float, default=0)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0)
    realized_day: Mapped[float] = mapped_column(Float, default=0)          # realized today (IST), resets each day
    day_key: Mapped[str] = mapped_column(String(10), default="")


class Strategy(Base):
    __tablename__ = "strategies"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    spec: Mapped[dict] = mapped_column(JSON)
    mode: Mapped[str] = mapped_column(String(10), default="off")           # off | paper | live
    account_id: Mapped[int | None] = mapped_column(ForeignKey("broker_accounts.id", ondelete="SET NULL"), nullable=True)
    last_target: Mapped[int] = mapped_column(Integer, default=0)
    last_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Backtest(Base):
    __tablename__ = "backtests"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    strategy_id: Mapped[int | None] = mapped_column(ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    params: Mapped[dict] = mapped_column(JSON)
    metrics: Mapped[dict] = mapped_column(JSON)
    equity: Mapped[list] = mapped_column(JSON)
    trades: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("broker_accounts.id", ondelete="SET NULL"), nullable=True)
    strategy_id: Mapped[int | None] = mapped_column(ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True)
    symbol: Mapped[str] = mapped_column(String(40))
    exchange: Mapped[str] = mapped_column(String(20))
    side: Mapped[str] = mapped_column(String(4))
    qty: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(12))                        # filled | sent | blocked | failed
    mode: Mapped[str] = mapped_column(String(10), default="paper")
    message: Mapped[str] = mapped_column(String(255), default="")
    broker_order_id: Mapped[str] = mapped_column(String(60), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class RiskLimits(Base):
    __tablename__ = "risk_limits"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    max_qty: Mapped[int] = mapped_column(Integer, default=100)
    max_order_value: Mapped[float] = mapped_column(Float, default=300_000)
    max_position_value: Mapped[float] = mapped_column(Float, default=500_000)
    max_orders_per_day: Mapped[int] = mapped_column(Integer, default=20)
    max_daily_loss: Mapped[float] = mapped_column(Float, default=5_000)
    window_start: Mapped[str] = mapped_column(String(5), default="09:20")
    window_end: Mapped[str] = mapped_column(String(5), default="15:15")
    allow_short: Mapped[bool] = mapped_column(Boolean, default=False)
    blocked: Mapped[list] = mapped_column(JSON, default=list)
    kill_switch: Mapped[bool] = mapped_column(Boolean, default=False)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), default="")


class Webhook(Base):
    """A TradingView alert endpoint. The secret token is shown once; only its SHA-256 hash is stored."""
    __tablename__ = "webhooks"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    mode: Mapped[str] = mapped_column(String(10), default="paper")          # paper | live
    account_id: Mapped[int | None] = mapped_column(ForeignKey("broker_accounts.id", ondelete="SET NULL"), nullable=True)
    hits: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class MarketCandle(Base):
    """1-minute candles built from the live tick feed (real recorded data for backtests and the AI analyst)."""
    __tablename__ = "market_candles"
    __table_args__ = (UniqueConstraint("symbol", "interval", "ts"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(40), index=True)
    interval: Mapped[str] = mapped_column(String(5), default="1m")
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float, default=0.0)
