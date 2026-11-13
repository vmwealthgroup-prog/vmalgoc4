from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    env: str = "development"                       # set "production" to enforce secret checks
    database_url: str = "sqlite:///./vmalgo.db"
    redis_url: str = ""                            # empty = in-process pub/sub (single instance only)
    secret_key: str = "dev-secret-change-me"       # JWT signing
    encryption_key: str = ""                       # Fernet key for broker API keys (required in production)
    access_token_minutes: int = 60 * 12
    cors_origins: str = "http://localhost:3000"
    allow_registration: bool = True
    auth_required: bool = False                    # default access mode: False = open (no login), True = login required. Changeable inside the app.
    admin_email: str = ""                          # this email becomes admin on registration
    live_trading_enabled: bool = False             # global hard switch. Live orders are impossible while false.
    runner_enabled: bool = True
    runner_interval_s: int = 30
    feed_source: str = "demo"                      # demo | crypto
    feed_symbols: str = "BTC/USD:CRYPTO,NIFTY:NSE,BANKNIFTY:NSE,RELIANCE:NSE"
    feed_in_api: bool = True                       # run feeder + runner inside the API process (simple hosting)
    crypto_exchange: str = "coinbase"
    # --- automation / compliance
    enforce_market_hours: bool = True
    market_holidays: str = ""
    square_off_time: str = "15:15"
    max_orders_per_second: int = 5
    breaker_default_trades: int = 10
    breaker_default_loss_pct: float = 3.0
    egress_ip_url: str = "https://api.ipify.org"
    crypto_feed: str = "coinbase"
    coinbase_ws_url: str = "wss://advanced-trade-ws.coinbase.com"
    # --- AI analyst (advisory only: it can never place an order)
    anthropic_api_key: str = ""
    ai_model: str = "claude-sonnet-5-5"
    ai_api_url: str = "https://api.anthropic.com/v1/messages"
    ai_max_per_hour: int = 20
    ai_timeout_s: int = 45
    # --- notifications
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    discord_webhook_url: str = ""
    notify_webhook_url: str = ""
    kite_market_protection: str = ""
    charges_json: str = ""


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.env == "production":
        if s.secret_key.startswith("dev-") or len(s.secret_key) < 32:
            raise RuntimeError("SECRET_KEY must be a random string of 32+ chars in production")
        if not s.encryption_key:
            raise RuntimeError("ENCRYPTION_KEY (Fernet) is required in production")
    return s
