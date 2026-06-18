from datamodel import Order, TradingState
from typing import Dict, List, Tuple, Any
import json


class Trader:
    LIMIT = 10
    MAX_TAKE_SPREAD = 19

    # Rules emit weighted votes; opposite signals cancel before execution.
    PAIR_RULES: Tuple[Tuple[str, str, str, int, int, float, float], ...] = (
        ("PEBBLES_M", "PEBBLES_XL", "rev", 100, 500, 120, 2.0),
        ("MICROCHIP_OVAL", "MICROCHIP_TRIANGLE", "rev", 200, 1000, 80, 2.0),
        ("PANEL_2X2", "PANEL_4X4", "mom", 200, 1000, 0, 2.0),
        ("OXYGEN_SHAKE_MORNING_BREATH", "OXYGEN_SHAKE_MINT", "mom", 200, 1000, 10, 2.0),
        ("SLEEP_POD_POLYESTER", "SLEEP_POD_COTTON", "rev", 500, 2000, 10, 2.0),
        ("UV_VISOR_YELLOW", "UV_VISOR_ORANGE", "mom", 500, 2000, 20, 2.0),
        ("SNACKPACK_CHOCOLATE", "SNACKPACK_VANILLA", "rev", 500, 2000, 2, 2.0),
        ("SNACKPACK_STRAWBERRY", "SNACKPACK_RASPBERRY", "rev", 500, 2000, 5, 1.5),
        ("SLEEP_POD_SUEDE", "SLEEP_POD_POLYESTER", "rev", 500, 2000, 160, 2.0),
        ("MICROCHIP_CIRCLE", "MICROCHIP_SQUARE", "mom", 1000, 4000, 20, 2.0),
        ("ROBOT_MOPPING", "ROBOT_IRONING", "mom", 50, 200, 120, 2.0),
        ("UV_VISOR_YELLOW", "UV_VISOR_MAGENTA", "rev", 500, 2000, 40, 2.0),
        ("UV_VISOR_YELLOW", "UV_VISOR_AMBER", "mom", 1000, 4000, 80, 2.0),
        ("OXYGEN_SHAKE_EVENING_BREATH", "OXYGEN_SHAKE_GARLIC", "mom", 100, 500, 250, 2.0),
        ("PANEL_1X4", "PANEL_4X4", "mom", 1000, 4000, 120, 2.0),
    )

    LEAD_RULES: Tuple[Tuple[str, str, str, int, int, float, float], ...] = (
        ("PEBBLES_XS", "PEBBLES_S", "mom", 500, 2000, 5, 1.0),
        ("TRANSLATOR_GRAPHITE_MIST", "TRANSLATOR_VOID_BLUE", "rev", 200, 1000, 20, 1.0),
        ("MICROCHIP_SQUARE", "MICROCHIP_OVAL", "mom", 200, 1000, 40, 1.0),
        ("UV_VISOR_RED", "UV_VISOR_YELLOW", "rev", 200, 1000, 10, 1.0),
        ("GALAXY_SOUNDS_BLACK_HOLES", "GALAXY_SOUNDS_SOLAR_WINDS", "rev", 500, 2000, 40, 1.0),
        ("ROBOT_MOPPING", "ROBOT_LAUNDRY", "rev", 200, 1000, 40, 1.0),
    )

    # Keep enough MICROCHIP_CIRCLE history for the longest lag rule.
    MICRO_CIRCLE = "MICROCHIP_CIRCLE"
    MICRO_CIRCLE_LAGS: Tuple[Tuple[str, int, float, float, float], ...] = (
        ("MICROCHIP_SQUARE", 100, 90.0, 25.0, 1.0),
        ("MICROCHIP_RECTANGLE", 150, 150.0, 40.0, 1.0),
    )
    CIRCLE_HISTORY_KEEP = 180

    def run(self, state: TradingState):
        data = self._load_data(getattr(state, "traderData", ""))
        timestamp = int(getattr(state, "timestamp", data.get("last_ts", -1)))

        # Timestamp resets mark a fresh replay/day.
        if data.get("last_ts", -1) > timestamp:
            data = self._empty_data()

        mids = self._snapshot_mids(state)
        self._update_circle_history(data, mids)
        scores: Dict[str, float] = {}

        for a, b, mode, fast, slow, threshold, weight in self.PAIR_RULES:
            if a not in mids or b not in mids:
                continue
            spread = mids[a] - mids[b]
            key = a + "|" + b
            signal = self._ema_signal(data, "p", key, spread, fast, slow)
            direction = self._direction(mode, signal, threshold)
            if direction:
                scores[a] = scores.get(a, 0.0) + weight * direction
                scores[b] = scores.get(b, 0.0) - weight * direction

        for leader, follower, mode, fast, slow, threshold, weight in self.LEAD_RULES:
            if leader not in mids or follower not in state.order_depths:
                continue
            key = leader + ">" + follower
            signal = self._ema_signal(data, "l", key, mids[leader], fast, slow)
            direction = self._direction(mode, signal, threshold)
            if direction:
                scores[follower] = scores.get(follower, 0.0) + weight * direction

        self._score_microchip_circle_lags(data, state, scores)

        result: Dict[str, List[Order]] = {}
        for symbol, score in scores.items():
            if symbol not in state.order_depths or score == 0:
                continue
            target = self.LIMIT if score > 0 else -self.LIMIT
            position = int(state.position.get(symbol, 0))
            orders = self._cross_to_target(symbol, state.order_depths[symbol], position, target)
            if orders:
                result[symbol] = orders

        data["last_ts"] = timestamp
        return result, 0, json.dumps(data, separators=(",", ":"))

    def _score_microchip_circle_lags(self, data: Dict[str, Any], state: TradingState, scores: Dict[str, float]) -> None:
        hist = data.get("circle_hist", [])
        if not isinstance(hist, list):
            return

        for follower, lag, entry, exit_threshold, weight in self.MICRO_CIRCLE_LAGS:
            if follower not in state.order_depths or len(hist) <= lag:
                continue

            signal = float(hist[-1]) - float(hist[-1 - lag])
            pos = int(state.position.get(follower, 0))

            # Inside the exit band, keep the current bias instead of flipping.
            direction = 0
            if signal > entry:
                direction = 1
            elif signal < -entry:
                direction = -1
            elif abs(signal) >= exit_threshold:
                if pos > 0:
                    direction = 1
                elif pos < 0:
                    direction = -1

            if direction:
                scores[follower] = scores.get(follower, 0.0) + weight * direction

    def _ema_signal(self, data: Dict[str, Any], bucket: str, key: str, value: float, fast: int, slow: int) -> float:
        store = data.setdefault(bucket, {})
        prev = store.get(key)
        if not isinstance(prev, list) or len(prev) != 2:
            fast_ema = value
            slow_ema = value
        else:
            fast_ema = float(prev[0])
            slow_ema = float(prev[1])

        fast_alpha = 2.0 / (fast + 1.0)
        slow_alpha = 2.0 / (slow + 1.0)
        fast_ema = fast_alpha * value + (1.0 - fast_alpha) * fast_ema
        slow_ema = slow_alpha * value + (1.0 - slow_alpha) * slow_ema
        store[key] = [round(fast_ema, 4), round(slow_ema, 4)]
        return fast_ema - slow_ema

    def _direction(self, mode: str, signal: float, threshold: float) -> int:
        direction = 0
        if signal > threshold:
            direction = 1
        elif signal < -threshold:
            direction = -1
        if mode == "rev":
            direction = -direction
        return direction

    def _cross_to_target(self, symbol: str, depth, position: int, target: int) -> List[Order]:
        orders: List[Order] = []
        if not depth.buy_orders or not depth.sell_orders:
            return orders

        best_bid = max(depth.buy_orders)
        best_ask = min(depth.sell_orders)
        if best_ask - best_bid > self.MAX_TAKE_SPREAD:
            return orders

        target = max(-self.LIMIT, min(self.LIMIT, int(target)))
        diff = target - int(position)

        if diff > 0:
            remaining = min(diff, self.LIMIT - position)
            for price in sorted(depth.sell_orders):
                if remaining <= 0:
                    break
                volume = int(-depth.sell_orders[price])
                if volume <= 0:
                    continue
                qty = min(remaining, volume)
                orders.append(Order(symbol, int(price), int(qty)))
                remaining -= qty

        elif diff < 0:
            remaining = min(-diff, self.LIMIT + position)
            for price in sorted(depth.buy_orders, reverse=True):
                if remaining <= 0:
                    break
                volume = int(depth.buy_orders[price])
                if volume <= 0:
                    continue
                qty = min(remaining, volume)
                orders.append(Order(symbol, int(price), -int(qty)))
                remaining -= qty

        return orders

    def _best_prices(self, depth):
        if not depth.buy_orders or not depth.sell_orders:
            return None
        best_bid = max(depth.buy_orders)
        best_ask = min(depth.sell_orders)
        return best_bid, best_ask, (best_bid + best_ask) / 2.0

    def _snapshot_mids(self, state: TradingState) -> Dict[str, float]:
        mids: Dict[str, float] = {}
        for symbol, depth in state.order_depths.items():
            best = self._best_prices(depth)
            if best is not None:
                mids[symbol] = best[2]
        return mids

    def _update_circle_history(self, data: Dict[str, Any], mids: Dict[str, float]) -> None:
        if self.MICRO_CIRCLE not in mids:
            return
        hist = data.get("circle_hist")
        if not isinstance(hist, list):
            hist = []
        hist.append(round(float(mids[self.MICRO_CIRCLE]), 4))
        if len(hist) > self.CIRCLE_HISTORY_KEEP:
            hist = hist[-self.CIRCLE_HISTORY_KEEP:]
        data["circle_hist"] = hist

    def _load_data(self, trader_data: str) -> Dict[str, Any]:
        if isinstance(trader_data, str) and trader_data:
            try:
                data = json.loads(trader_data)
                if isinstance(data, dict):
                    for bucket in ("p", "l"):
                        if not isinstance(data.get(bucket), dict):
                            data[bucket] = {}
                    if not isinstance(data.get("circle_hist"), list):
                        data["circle_hist"] = []
                    if not isinstance(data.get("last_ts"), int):
                        data["last_ts"] = -1
                    return data
            except (TypeError, ValueError, json.JSONDecodeError):
                return self._empty_data()
        return self._empty_data()

    def _empty_data(self) -> Dict[str, Any]:
        return {"p": {}, "l": {}, "circle_hist": [], "last_ts": -1}
