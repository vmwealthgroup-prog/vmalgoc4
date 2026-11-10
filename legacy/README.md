# Legacy: static marketing site + command-line tools
The original VM Algo project, kept intact. The full-stack app in `../backend` and `../frontend` supersedes the dashboards,
but these remain useful:
- `*.html`, `css/`, `js/`  static marketing site (deploy anywhere, or serve as your public landing page)
- `strategies/`, `backtest/`, `data/`, `risk/`  CLI strategies, walk-forward tester, crypto feed, risk gate
- `openalgo/setup.sh <broker>`  installs and starts upstream OpenAlgo (the broker gateway the app connects to)
Run its tests with `python -m unittest discover -s tests`.
