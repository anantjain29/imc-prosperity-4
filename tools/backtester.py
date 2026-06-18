#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import math
import os
import re
import sys
import types
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from json import JSONEncoder
from pathlib import Path
from contextlib import redirect_stdout
from typing import Any, Dict, Iterable, List, Optional, Tuple


Symbol = str
Product = str
Position = int


@dataclass
class Listing:
    symbol: Symbol
    product: Product
    denomination: str = "SEASHELLS"


@dataclass
class Order:
    symbol: Symbol
    price: int
    quantity: int


@dataclass
class OrderDepth:
    buy_orders: Dict[int, int] = field(default_factory=dict)
    sell_orders: Dict[int, int] = field(default_factory=dict)


@dataclass
class Trade:
    symbol: Symbol
    price: int
    quantity: int
    buyer: str = ""
    seller: str = ""
    timestamp: int = 0


@dataclass
class ConversionObservation:
    bidPrice: float = 0.0
    askPrice: float = 0.0
    transportFees: float = 0.0
    exportTariff: float = 0.0
    importTariff: float = 0.0
    sunlight: float = 0.0
    humidity: float = 0.0


@dataclass
class Observation:
    plainValueObservations: Dict[str, float] = field(default_factory=dict)
    conversionObservations: Dict[str, ConversionObservation] = field(default_factory=dict)


@dataclass
class TradingState:
    traderData: str
    timestamp: int
    listings: Dict[Symbol, Listing]
    order_depths: Dict[Symbol, OrderDepth]
    own_trades: Dict[Symbol, List[Trade]]
    market_trades: Dict[Symbol, List[Trade]]
    position: Dict[Product, Position]
    observations: Observation


class ProsperityEncoder(JSONEncoder):
    def default(self, obj: Any) -> Any:
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        return super().default(obj)


def install_datamodel() -> None:
    module = types.ModuleType("datamodel")
    module.Symbol = Symbol
    module.Product = Product
    module.Position = Position
    module.Listing = Listing
    module.Order = Order
    module.OrderDepth = OrderDepth
    module.Trade = Trade
    module.ConversionObservation = ConversionObservation
    module.Observation = Observation
    module.TradingState = TradingState
    module.ProsperityEncoder = ProsperityEncoder
    sys.modules["datamodel"] = module


ROUND_LIMITS: Dict[int, Dict[str, int]] = {
    3: {
        "HYDROGEL_PACK": 200,
        "VELVETFRUIT_EXTRACT": 200,
        "VEV_4000": 300,
        "VEV_4500": 300,
        "VEV_5000": 300,
        "VEV_5100": 300,
        "VEV_5200": 300,
        "VEV_5300": 300,
        "VEV_5400": 300,
        "VEV_5500": 300,
        "VEV_6000": 300,
        "VEV_6500": 300,
    },
    4: {
        "HYDROGEL_PACK": 200,
        "VELVETFRUIT_EXTRACT": 200,
        "VEV_4000": 300,
        "VEV_4500": 300,
        "VEV_5000": 300,
        "VEV_5100": 300,
        "VEV_5200": 300,
        "VEV_5300": 300,
        "VEV_5400": 300,
        "VEV_5500": 300,
        "VEV_6000": 300,
        "VEV_6500": 300,
    },
}


def round5_limits(products: Iterable[str]) -> Dict[str, int]:
    return {product: 10 for product in products}


PRICE_RE = re.compile(r"prices_round_(?P<round>\d+)_day_(?P<day>-?\d+)\.csv$")


@dataclass
class DayResult:
    day: int
    ticks: int
    fills: int
    pnl: float
    product_pnl: Dict[str, float]


def parse_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(float(value))


def load_trader(trader_path: Path):
    install_datamodel()
    spec = importlib.util.spec_from_file_location("submission_trader", trader_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load trader: {trader_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "Trader"):
        raise RuntimeError(f"{trader_path} does not define Trader")
    return module.Trader()


def csv_files(dataset: Path) -> List[Tuple[int, int, Path, Optional[Path]]]:
    out: List[Tuple[int, int, Path, Optional[Path]]] = []
    for price_path in sorted(dataset.glob("prices_round_*_day_*.csv")):
        match = PRICE_RE.search(price_path.name)
        if not match:
            continue
        round_no = int(match.group("round"))
        day = int(match.group("day"))
        trade_path = dataset / f"trades_round_{round_no}_day_{day}.csv"
        out.append((round_no, day, price_path, trade_path if trade_path.exists() else None))
    if not out:
        raise RuntimeError(f"No prices_round_*_day_*.csv files found in {dataset}")
    return out


def load_market_trades(path: Optional[Path]) -> Dict[int, Dict[str, List[Trade]]]:
    trades: Dict[int, Dict[str, List[Trade]]] = {}
    if path is None:
        return trades
    with path.open(newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            timestamp = parse_int(row.get("timestamp"))
            symbol = row.get("symbol") or row.get("product") or ""
            if not symbol:
                continue
            trade = Trade(
                symbol=symbol,
                price=parse_int(row.get("price")),
                quantity=abs(parse_int(row.get("quantity"))),
                buyer=row.get("buyer") or "",
                seller=row.get("seller") or "",
                timestamp=timestamp,
            )
            trades.setdefault(timestamp, {}).setdefault(symbol, []).append(trade)
    return trades


def grouped_books(price_path: Path):
    with price_path.open(newline="") as f:
        reader = csv.reader(f, delimiter=";")
        try:
            header = next(reader)
        except StopIteration:
            return

        columns = {name: index for index, name in enumerate(header)}
        timestamp_index = columns.get("timestamp")
        product_index = columns["product"]
        mid_index = columns.get("mid_price")
        bid_columns = [
            (columns[f"bid_price_{i}"], columns[f"bid_volume_{i}"])
            for i in range(1, 4)
            if f"bid_price_{i}" in columns and f"bid_volume_{i}" in columns
        ]
        ask_columns = [
            (columns[f"ask_price_{i}"], columns[f"ask_volume_{i}"])
            for i in range(1, 4)
            if f"ask_price_{i}" in columns and f"ask_volume_{i}" in columns
        ]

        current_ts: Optional[int] = None
        depths: Dict[str, OrderDepth] = {}
        mids: Dict[str, float] = {}
        for row in reader:
            row_length = len(row)
            timestamp = int(row[timestamp_index]) if timestamp_index is not None else 0
            if current_ts is None:
                current_ts = timestamp
            if timestamp != current_ts:
                yield current_ts, depths, mids
                current_ts = timestamp
                depths = {}
                mids = {}

            product = row[product_index]
            depth = OrderDepth()
            for price_index, volume_index in bid_columns:
                if price_index >= row_length or volume_index >= row_length:
                    continue
                price = row[price_index]
                volume = row[volume_index]
                if price != "" and volume != "":
                    depth.buy_orders[int(price)] = abs(int(volume))
            for price_index, volume_index in ask_columns:
                if price_index >= row_length or volume_index >= row_length:
                    continue
                price = row[price_index]
                volume = row[volume_index]
                if price != "" and volume != "":
                    depth.sell_orders[int(price)] = -abs(int(volume))

            depths[product] = depth
            if mid_index is not None and mid_index < row_length:
                mid_value = row[mid_index]
                if mid_value != "":
                    mid = float(mid_value)
                    if math.isfinite(mid):
                        mids[product] = mid
        if current_ts is not None:
            yield current_ts, depths, mids


def normalize_return(value: Any) -> Tuple[Dict[str, List[Order]], str]:
    if isinstance(value, tuple):
        if len(value) == 3:
            orders, _conversions, trader_data = value
            return orders or {}, str(trader_data or "")
        if len(value) == 2:
            orders, _conversions = value
            return orders or {}, ""
    if isinstance(value, dict):
        return value, ""
    raise RuntimeError(f"Unexpected Trader.run return value: {type(value)!r}")


def clamp_order_qty(product: str, qty: int, position: Dict[str, int], limits: Dict[str, int]) -> int:
    limit = limits.get(product, 10)
    pos = position.get(product, 0)
    if qty > 0:
        return min(qty, limit - pos)
    if qty < 0:
        return -min(-qty, limit + pos)
    return 0


def execute_orders(
    orders: Dict[str, List[Order]],
    depths: Dict[str, OrderDepth],
    position: Dict[str, int],
    cash: Dict[str, float],
    limits: Dict[str, int],
    timestamp: int,
    market_trades: Optional[Dict[str, List[Trade]]] = None,
    fill_model: str = "visible_book_crossing",
) -> Dict[str, List[Trade]]:
    market_trades = market_trades or {}
    own: Dict[str, List[Trade]] = {}
    for product, product_orders in orders.items():
        depth = depths.get(product)
        if depth is None:
            continue
        for order in product_orders:
            qty = clamp_order_qty(product, int(order.quantity), position, limits)
            if qty == 0:
                continue
            if qty > 0:
                remaining = qty
                for ask_price in sorted(depth.sell_orders):
                    available = -depth.sell_orders[ask_price]
                    if remaining <= 0 or ask_price > order.price:
                        break
                    fill = min(remaining, available)
                    if fill <= 0:
                        continue
                    remaining -= fill
                    depth.sell_orders[ask_price] += fill
                    position[product] = position.get(product, 0) + fill
                    cash[product] = cash.get(product, 0.0) - ask_price * fill
                    own.setdefault(product, []).append(Trade(product, ask_price, fill, "SUBMISSION", "", timestamp))
                depth.sell_orders = {p: v for p, v in depth.sell_orders.items() if v < 0}
                if fill_model == "market_trades" and remaining > 0:
                    for market_trade in market_trades.get(product, []):
                        if remaining <= 0:
                            break
                        if market_trade.price > order.price or market_trade.quantity <= 0:
                            continue
                        fill = min(remaining, market_trade.quantity)
                        remaining -= fill
                        market_trade.quantity -= fill
                        position[product] = position.get(product, 0) + fill
                        cash[product] = cash.get(product, 0.0) - order.price * fill
                        own.setdefault(product, []).append(
                            Trade(product, order.price, fill, "SUBMISSION", "", timestamp)
                        )
            else:
                remaining = -qty
                for bid_price in sorted(depth.buy_orders, reverse=True):
                    available = depth.buy_orders[bid_price]
                    if remaining <= 0 or bid_price < order.price:
                        break
                    fill = min(remaining, available)
                    if fill <= 0:
                        continue
                    remaining -= fill
                    depth.buy_orders[bid_price] -= fill
                    position[product] = position.get(product, 0) - fill
                    cash[product] = cash.get(product, 0.0) + bid_price * fill
                    own.setdefault(product, []).append(Trade(product, bid_price, fill, "", "SUBMISSION", timestamp))
                depth.buy_orders = {p: v for p, v in depth.buy_orders.items() if v > 0}
                if fill_model == "market_trades" and remaining > 0:
                    for market_trade in market_trades.get(product, []):
                        if remaining <= 0:
                            break
                        if market_trade.price < order.price or market_trade.quantity <= 0:
                            continue
                        fill = min(remaining, market_trade.quantity)
                        remaining -= fill
                        market_trade.quantity -= fill
                        position[product] = position.get(product, 0) - fill
                        cash[product] = cash.get(product, 0.0) + order.price * fill
                        own.setdefault(product, []).append(
                            Trade(product, order.price, fill, "", "SUBMISSION", timestamp)
                        )
    return own


def mark_pnl(cash: Dict[str, float], position: Dict[str, int], mids: Dict[str, float]) -> Dict[str, float]:
    products = set(cash) | set(position) | set(mids)
    return {p: cash.get(p, 0.0) + position.get(p, 0) * mids.get(p, 0.0) for p in products}


def limits_for(round_no: int, products: Iterable[str]) -> Dict[str, int]:
    if round_no == 5:
        return round5_limits(products)
    return dict(ROUND_LIMITS.get(round_no, {}))


def run_day(
    trader_path: Path,
    round_no: int,
    day: int,
    price_path: Path,
    trade_path: Optional[Path],
    fill_model: str = "visible_book_crossing",
) -> DayResult:
    trader = load_trader(trader_path)
    market_by_ts = load_market_trades(trade_path)
    position: Dict[str, int] = {}
    cash: Dict[str, float] = {}
    own_trades: Dict[str, List[Trade]] = {}
    trader_data = ""
    last_mids: Dict[str, float] = {}
    ticks = 0
    fills = 0
    limits: Dict[str, int] = {}
    listings: Dict[str, Listing] = {}

    for timestamp, depths, mids in grouped_books(price_path):
        if not limits:
            limits = limits_for(round_no, depths.keys())
        last_mids.update(mids)
        if listings.keys() != depths.keys():
            listings = {p: Listing(p, p, "SEASHELLS") for p in depths}
        market_trades = market_by_ts.get(timestamp, {})
        state = TradingState(
            traderData=trader_data,
            timestamp=timestamp,
            listings=listings,
            order_depths=depths,
            own_trades=own_trades,
            market_trades=market_trades,
            position=dict(position),
            observations=Observation(),
        )
        with redirect_stdout(io.StringIO()):
            orders, trader_data = normalize_return(trader.run(state))
        own_trades = execute_orders(
            orders,
            depths,
            position,
            cash,
            limits,
            timestamp,
            market_trades,
            fill_model,
        )
        fills += sum(len(v) for v in own_trades.values())
        ticks += 1

    product_pnl = mark_pnl(cash, position, last_mids)
    return DayResult(day=day, ticks=ticks, fills=fills, pnl=sum(product_pnl.values()), product_pnl=product_pnl)


def format_money(value: float) -> str:
    return f"{value:,.2f}"


def run_backtest(
    trader: Path,
    dataset: Path,
    fill_model: str = "visible_book_crossing",
    jobs: int = 1,
) -> List[DayResult]:
    files = csv_files(dataset)
    if jobs < 0:
        raise ValueError("jobs must be zero or greater")
    worker_count = min(len(files), jobs or (os.cpu_count() or 1))
    work = [
        (trader, round_no, day, price_path, trade_path, fill_model)
        for round_no, day, price_path, trade_path in files
    ]
    if worker_count <= 1:
        return [run_day(*item) for item in work]
    with ProcessPoolExecutor(max_workers=worker_count) as executor:
        return list(executor.map(_run_day_job, work))


def _run_day_job(
    work: Tuple[Path, int, int, Path, Optional[Path], str],
) -> DayResult:
    return run_day(*work)


def print_summary(results: List[DayResult], products: str) -> None:
    print("DAY    TICKS    FILLS      FINAL_PNL")
    for result in results:
        print(f"{result.day:>3} {result.ticks:>8} {result.fills:>8} {format_money(result.pnl):>14}")
    total = sum(r.pnl for r in results)
    print(f"TOTAL {'':>7} {'':>8} {format_money(total):>14}")
    if products == "off":
        return
    aggregate: Dict[str, float] = {}
    for result in results:
        for product, pnl in result.product_pnl.items():
            aggregate[product] = aggregate.get(product, 0.0) + pnl
    rows = sorted(aggregate.items(), key=lambda kv: abs(kv[1]), reverse=True)
    if products == "summary":
        rows = rows[:15]
    print("\nPRODUCT_PNL")
    for product, pnl in rows:
        print(f"{product:<36} {format_money(pnl):>14}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Lightweight IMC-style Python backtester")
    parser.add_argument("--trader", required=True, type=Path)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--products", choices=("summary", "full", "off"), default="summary")
    parser.add_argument(
        "--fill-model",
        choices=("visible_book_crossing", "market_trades"),
        default="visible_book_crossing",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=0,
        help="parallel day workers (default: auto, use 1 for sequential)",
    )
    args = parser.parse_args()

    results = run_backtest(args.trader, args.dataset, args.fill_model, args.jobs)
    print_summary(results, args.products)


if __name__ == "__main__":
    main()
