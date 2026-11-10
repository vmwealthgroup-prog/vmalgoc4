from abc import ABC, abstractmethod


class BrokerError(Exception):
    pass


class Broker(ABC):
    """Everything the platform needs from a broker. Positions are dicts:
    {symbol, exchange, qty (signed), avg_price, ltp, pnl}."""
    @abstractmethod
    def place_order(self, *, symbol, exchange, side, qty, price_hint, product="MIS", strategy="VMAlgo") -> dict: ...
    @abstractmethod
    def positions(self) -> list[dict]: ...
    @abstractmethod
    def holdings(self) -> list[dict]: ...
    @abstractmethod
    def funds(self) -> dict: ...
    @abstractmethod
    def quote(self, symbol, exchange) -> dict: ...
    def daily_pnl(self) -> float:
        """Today's P&L used by the daily-loss guard. Brokers report day P&L in positions; the paper broker overrides this."""
        return sum(p.get("pnl", 0) for p in self.positions())

    def history_client(self):  # object with .history() for the data layer; None for paper
        return None
