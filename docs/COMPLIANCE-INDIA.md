# Automated trading in India: what to know before you go live

*This is a plain summary of broker and industry write-ups read while building this project, not legal advice. Read the SEBI circular and your broker's notice yourself, and ask your broker if unsure.*

## The rules in short
SEBI's retail algorithmic trading framework (circular of February 2025) was implemented through NSE's standards and became fully applicable on **1 April 2026**. As described by brokers:
- Orders sent through a broker **API must come from a static IP address you have registered with your broker.**
- Logins use **two-factor / OAuth**, and each client or vendor has its own API key. That is why brokers such as Zerodha need a fresh login every trading day.
- Orders carry an **algo identifier**, so the exchange can tell algo orders apart.
- There is an **order-rate threshold of about 10 orders per second**. Below it, your own algo does not need to be registered as a strategy; above it, it does.
- A **platform that provides algos to other people** is treated as an algo provider and generally must be empanelled with the exchange and work through a broker. Running software only for yourself is different from offering it to customers.

## What VM Algo does about it
| Requirement | In VM Algo |
|---|---|
| Static IP | Brokers page shows the server's outbound IP so you can register it. You must host on a fixed (elastic) IP. |
| Daily 2FA login | Zerodha daily login flow built in; alert when it has expired. This step is deliberately manual. |
| Order rate | Global cap `MAX_ORDERS_PER_SECOND` (default 5), enforced across API, webhooks and the worker. |
| Algo tagging | Orders to Zerodha carry a `tag` naming the strategy. The exchange algo ID itself is assigned through your broker. |
| Audit trail | Every order decision, including blocked ones, is stored with its reason. |
| Real-money safety | Live trading is off by default, needs login mode, a per-account switch, and passes the risk gate. |

## Crypto
Crypto has its own legal and tax treatment in India, separate from SEBI's algo framework above (gains and transfers can be taxed and subject to withholding). Rules change: check the current position before trading it, and keep records.

## What it does NOT do
- It does **not** register strategies with an exchange or make you an empanelled algo provider.
- It does **not** make "full automation" legal for you: that depends on your broker, your IP registration and your own situation.
- If you host it for **other people**, get proper advice first. That is the line between a personal tool and a regulated service.
- Holiday calendars are not built in: set `MARKET_HOLIDAYS` yourself each year.
