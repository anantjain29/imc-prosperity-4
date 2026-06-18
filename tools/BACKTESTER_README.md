# Python Backtester

`backtester.py` is a lightweight local simulator for the included IMC-style
traders and CSV datasets.

## Usage

Run from the repo root:

```bash
python3 tools/backtester.py --trader round3/trader.py --dataset round3/datasets
```

Optional product output:

```bash
python3 tools/backtester.py --trader round5/trader.py --dataset round5/datasets --products full
python3 tools/backtester.py --trader round5/trader.py --dataset round5/datasets --products off
```

Optional fill model:

```bash
python3 tools/backtester.py --trader round3/trader.py --dataset round3/datasets --fill-model market_trades
```

Days run in parallel by default. Use `--jobs 1` for sequential execution or set
an explicit worker count with, for example, `--jobs 2`.

## Fill Model

The simulator replays each timestamp from the price CSV and builds an
IMC-compatible `TradingState`.

The default `visible_book_crossing` model fills orders only when they cross
visible book levels:

- buy orders fill against asks priced at or below the submitted buy price;
- sell orders fill against bids priced at or above the submitted sell price;
- fills consume visible volume level by level;
- orders are clipped to product position limits.

The `market_trades` model keeps that behavior and also uses same-timestamp
market trades to approximate fills for any remaining passive quantity. Passive
buys can fill against trades at or below the order price, and passive sells can
fill against trades at or above the order price. These fills execute at the
submitted order price and consume the available market-trade volume.

## PnL

Cash changes when orders fill. At the end of each day, open positions are marked
to the latest mid price from that day:

```text
product_pnl = cash + position * last_mid_price
```

The final day PnL is the sum of all product PnLs.

## Simplifications

This is intentionally small and readable. It does not model hidden liquidity,
queue priority, exchange latency, partial matching rules beyond visible levels,
or conversion mechanics. It is best used for fast strategy iteration and sanity
checks.
