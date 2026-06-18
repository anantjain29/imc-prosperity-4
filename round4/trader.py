from datamodel import OrderDepth, TradingState, Order
from typing import Dict, List, Optional
from collections import defaultdict, deque


class Trader:
    LIMITS: Dict[str, int] = {
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
    }

    # HYDROGEL keeps separate flow and passive controls from the shared path.
    HYDROGEL_BUY_TH = 9992.0
    HYDROGEL_SELL_TH = 10015.0
    HYDROGEL_MAX_SPREAD = 28
    HYDROGEL_MAX_TAKE = 70
    HYDROGEL_PASSIVE_SIZE = 14
    HYDROGEL_FLOW_DECAY = 0.92
    HYDROGEL_FLOW_CAP = 8.0
    HYDROGEL_SKEW_MULT = 0.75
    HYDROGEL_SKEW_CAP = 2.0
    HYDROGEL_BOT_WEIGHTS = {
        "Mark 14": 1.15,
        "Mark 38": -1.05,
        "Mark 22": 0.15,
    }

    # Base crossing bands.
    BASE_BUY = {
        "HYDROGEL_PACK": HYDROGEL_BUY_TH,
        "VELVETFRUIT_EXTRACT": 5245.0,
        "VEV_4000": 1225.0,
        "VEV_4500": 742.0,
        "VEV_5000": 254.0,
        "VEV_5100": 150.0,
        "VEV_5200": 92.0,
        "VEV_5300": 45.0,
        "VEV_5400": 14.5,
        "VEV_5500": 3.0,
    }

    BASE_SELL = {
        "HYDROGEL_PACK": HYDROGEL_SELL_TH,
        "VELVETFRUIT_EXTRACT": 5270.5,
        "VEV_4000": 1266.0,
        "VEV_4500": 766.0,
        "VEV_5000": 272.0,
        "VEV_5100": 178.0,
        "VEV_5200": 105.0,
        "VEV_5300": 52.0,
        "VEV_5400": 17.0,
        "VEV_5500": 6.0,
    }

    BASE_HYBRID_BUY = {
        "VELVETFRUIT_EXTRACT": 5230.0,
        "VEV_4500": 722.0,
        "VEV_5000": 232.0,
    }

    BASE_HYBRID_SELL = {
        "VELVETFRUIT_EXTRACT": 5262.0,
        "VEV_4500": 768.0,
        "VEV_5000": 274.0,
    }

    VOUCHERS = {
        "VEV_4000",
        "VEV_4500",
        "VEV_5000",
        "VEV_5100",
        "VEV_5200",
        "VEV_5300",
        "VEV_5400",
        "VEV_5500",
    }

    SYN_UNDER_MAX_DISAGREE = 3.0
    SYN_UNDER_DIRECT_BLEND = 0.25

    UNDERLYING_LOOKBACK = 5
    VOUCHER_CRASH_TREND = 5.0
    VOUCHER_CRASH_COOLDOWN_TICKS = 3
    RISK_COOLDOWN_TICKS = 2

    # Option fair = a + b * (underlying_mid - reference).
    OPTION_FAIR_MODEL = {
        "VEV_4000": (1250.0, 1.00),
        "VEV_4500": (750.0, 1.00),
        "VEV_5000": (253.5, 0.96),
        "VEV_5100": (163.0, 0.86),
        "VEV_5200": (90.5, 0.68),
        "VEV_5300": (42.0, 0.42),
        "VEV_5400": (13.0, 0.18),
        "VEV_5500": (5.0, 0.08),
    }

    OPTION_FAIR_REF_UNDER = 5250.0

    HYBRID_FAIR_GUARD = {
        "VEV_4500": 11.0,
        "VEV_5000": 8.0,
    }

    # Risk guard tables collapse room to inventory reduction when triggered.
    RISK_MAX_SPREAD = {
        "HYDROGEL_PACK": HYDROGEL_MAX_SPREAD,
        "VELVETFRUIT_EXTRACT": 8,
        "VEV_4500": 20,
        "VEV_5000": 9,
        "VEV_5500": 4,
    }

    RISK_MIN_VISIBLE = {
        "VELVETFRUIT_EXTRACT": 35,
        "VEV_4500": 14,
        "VEV_5000": 14,
        "VEV_5500": 8,
    }

    RISK_MAX_TICK_MOVE = {
        "VELVETFRUIT_EXTRACT": 8.0,
        "VEV_4500": 12.0,
        "VEV_5000": 8.0,
        "VEV_5500": 3.0,
    }

    FAIR_LOOKBACK = 160

    MAKER_PRODUCTS = {
        "HYDROGEL_PACK",
        "VELVETFRUIT_EXTRACT",
        "VEV_4000",
        "VEV_4500",
        "VEV_5000",
        "VEV_5100",
        "VEV_5200",
        "VEV_5300",
        "VEV_5400",
        "VEV_5500",
    }

    MAKER_MAX_SPREAD = {
        "HYDROGEL_PACK": HYDROGEL_MAX_SPREAD,
        "VELVETFRUIT_EXTRACT": 10,
        "VEV_4000": 24,
        "VEV_4500": 22,
        "VEV_5000": 10,
        "VEV_5100": 8,
        "VEV_5200": 6,
        "VEV_5300": 5,
        "VEV_5400": 4,
        "VEV_5500": 3,
    }

    MAKER_EDGE = {
        "HYDROGEL_PACK": 3.0,
        "VELVETFRUIT_EXTRACT": 1.5,
        "VEV_4000": 4.0,
        "VEV_4500": 4.0,
        "VEV_5000": 2.0,
        "VEV_5100": 1.5,
        "VEV_5200": 1.0,
        "VEV_5300": 0.8,
        "VEV_5400": 0.5,
        "VEV_5500": 0.4,
    }

    MAKER_QTY = {
        "HYDROGEL_PACK": HYDROGEL_PASSIVE_SIZE,
        "VELVETFRUIT_EXTRACT": 8,
        "VEV_4000": 8,
        "VEV_4500": 8,
        "VEV_5000": 10,
        "VEV_5100": 10,
        "VEV_5200": 10,
        "VEV_5300": 12,
        "VEV_5400": 14,
        "VEV_5500": 16,
    }

    FULL_INV_FRAC = 0.82
    ZERO_BID_PRODUCTS = {"VEV_6000", "VEV_6500"}
    ZERO_BID_QTY = 30

    def __init__(self):
        self.mid_history = defaultdict(lambda: deque(maxlen=self.FAIR_LOOKBACK))
        self.risk_cooldown = defaultdict(int)
        self.voucher_crash_cooldown = defaultdict(int)
        self.hydrogel_flow = 0.0
        self.hydrogel_last_ts = None

    def clamp(self, x: float, lo: float, hi: float) -> float:
        if x < lo:
            return lo
        if x > hi:
            return hi
        return x

    def update_hydrogel_flow(self, state: TradingState):
        ts = getattr(state, "timestamp", 0) or 0
        if self.hydrogel_last_ts is None:
            decay = self.HYDROGEL_FLOW_DECAY
        else:
            decay = self.HYDROGEL_FLOW_DECAY ** max(1.0, (ts - self.hydrogel_last_ts) / 100.0)

        self.hydrogel_flow *= decay
        if abs(self.hydrogel_flow) < 0.02:
            self.hydrogel_flow = 0.0

        for trade in state.market_trades.get("HYDROGEL_PACK", []) or []:
            buyer = getattr(trade, "buyer", None) or ""
            seller = getattr(trade, "seller", None) or ""
            quantity = abs(int(getattr(trade, "quantity", 0) or 0))
            if quantity <= 0:
                continue

            size = self.clamp(quantity / 4.0, 0.5, 2.5)

            if buyer in self.HYDROGEL_BOT_WEIGHTS:
                self.hydrogel_flow = self.clamp(
                    self.hydrogel_flow + self.HYDROGEL_BOT_WEIGHTS[buyer] * size,
                    -self.HYDROGEL_FLOW_CAP,
                    self.HYDROGEL_FLOW_CAP,
                )

            if seller in self.HYDROGEL_BOT_WEIGHTS:
                self.hydrogel_flow = self.clamp(
                    self.hydrogel_flow - self.HYDROGEL_BOT_WEIGHTS[seller] * size,
                    -self.HYDROGEL_FLOW_CAP,
                    self.HYDROGEL_FLOW_CAP,
                )

        self.hydrogel_last_ts = ts

    def hydrogel_flow_skew(self) -> float:
        return self.clamp(
            self.hydrogel_flow * self.HYDROGEL_SKEW_MULT,
            -self.HYDROGEL_SKEW_CAP,
            self.HYDROGEL_SKEW_CAP,
        )

    def mid_from_depth(self, depth: Optional[OrderDepth]) -> Optional[float]:
        if depth is None or not depth.buy_orders or not depth.sell_orders:
            return None

        best_bid = max(depth.buy_orders.keys())
        best_ask = min(depth.sell_orders.keys())
        if best_bid >= best_ask:
            return None

        return 0.5 * (best_bid + best_ask)

    def visible_volume(self, depth: OrderDepth):
        bid_volume = sum(v for v in depth.buy_orders.values() if v > 0)
        ask_volume = sum(-v for v in depth.sell_orders.values() if v < 0)
        return bid_volume, ask_volume

    def l1_imbalance(self, depth: OrderDepth) -> float:
        if not depth.buy_orders or not depth.sell_orders:
            return 0.0

        best_bid = max(depth.buy_orders.keys())
        best_ask = min(depth.sell_orders.keys())
        bid_volume = depth.buy_orders.get(best_bid, 0)
        ask_volume = -depth.sell_orders.get(best_ask, 0)
        total = bid_volume + ask_volume
        if total <= 0:
            return 0.0

        return (bid_volume - ask_volume) / total

    def imbalance_threshold_shift(self, product: str, depth: OrderDepth) -> float:
        if product == "VELVETFRUIT_EXTRACT":
            return 0.8 * self.l1_imbalance(depth)
        return 0.0

    def update_mid_history(self, state: TradingState):
        for product, depth in state.order_depths.items():
            mid = self.mid_from_depth(depth)
            if mid is not None:
                self.mid_history[product].append(mid)

    def get_underlying_trend(self) -> float:
        hist = self.mid_history["VELVETFRUIT_EXTRACT"]
        if len(hist) < self.UNDERLYING_LOOKBACK + 1:
            return 0.0
        return hist[-1] - hist[-(self.UNDERLYING_LOOKBACK + 1)]

    def rolling_mean(self, product: str, n: int, fallback: float) -> float:
        hist = self.mid_history[product]
        if len(hist) < max(8, n // 5):
            return fallback
        values = list(hist)[-min(n, len(hist)):]
        return sum(values) / len(values)

    def synthetic_under_mid(self, state: TradingState) -> Optional[float]:
        direct = self.mid_from_depth(state.order_depths.get("VELVETFRUIT_EXTRACT"))
        estimates = []
        for voucher, strike in (("VEV_4000", 4000), ("VEV_4500", 4500)):
            mid = self.mid_from_depth(state.order_depths.get(voucher))
            if mid is not None:
                estimates.append(mid + strike)

        if len(estimates) >= 2 and max(estimates) - min(estimates) <= self.SYN_UNDER_MAX_DISAGREE:
            synthetic = sum(estimates) / len(estimates)
            if direct is None:
                return synthetic
            return self.SYN_UNDER_DIRECT_BLEND * direct + (1.0 - self.SYN_UNDER_DIRECT_BLEND) * synthetic

        return direct

    def option_fair(self, product: str, under_mid: Optional[float]) -> Optional[float]:
        if product not in self.OPTION_FAIR_MODEL or under_mid is None:
            return None

        a, b = self.OPTION_FAIR_MODEL[product]
        fair = a + b * (under_mid - self.OPTION_FAIR_REF_UNDER)

        return max(0.0, fair)

    def passive_fair(self, product: str, mid: float, under_mid: Optional[float]) -> Optional[float]:
        if product == "HYDROGEL_PACK":
            return self.rolling_mean(product, 120, mid)
        if product == "VELVETFRUIT_EXTRACT":
            return self.rolling_mean(product, 80, mid)

        fair = self.option_fair(product, under_mid)
        return fair if fair is not None else mid

    def hydrogel_passive_quotes(
        self,
        depth: OrderDepth,
        position: int,
        limit: int,
        buy_room: int,
        sell_room: int,
        buy_edge: float,
        sell_edge: float,
    ) -> List[Order]:
        if not depth.buy_orders or not depth.sell_orders:
            return []

        best_bid = max(depth.buy_orders.keys())
        best_ask = min(depth.sell_orders.keys())
        if best_bid >= best_ask:
            return []

        spread = best_ask - best_bid
        if spread < 2 or spread > self.HYDROGEL_MAX_SPREAD:
            return []

        orders: List[Order] = []
        pos_after = position
        inv_frac = pos_after / float(limit)
        base_qty = self.HYDROGEL_PASSIVE_SIZE

        if buy_room > 0 and pos_after < limit:
            buy_price = min(best_bid + 1, int(buy_edge))
            if best_bid < buy_price < best_ask and buy_price <= buy_edge:
                qty = min(
                    buy_room,
                    limit - pos_after,
                    max(1, int(base_qty * self.clamp(1.0 - inv_frac, 0.35, 1.65))),
                )
                if qty > 0:
                    orders.append(Order("HYDROGEL_PACK", int(buy_price), int(qty)))
                    pos_after += qty

        if sell_room > 0 and pos_after > -limit:
            sell_price = max(best_ask - 1, int(sell_edge))
            if best_bid < sell_price < best_ask and sell_price >= sell_edge:
                qty = min(
                    sell_room,
                    pos_after + limit,
                    max(1, int(base_qty * self.clamp(1.0 + inv_frac, 0.35, 1.65))),
                )
                if qty > 0:
                    orders.append(Order("HYDROGEL_PACK", int(sell_price), -int(qty)))

        return orders

    def passive_edge_orders(
        self,
        product: str,
        depth: OrderDepth,
        position: int,
        limit: int,
        buy_room: int,
        sell_room: int,
        mid: float,
        under_mid: Optional[float],
    ) -> List[Order]:
        if product not in self.MAKER_PRODUCTS or not depth.buy_orders or not depth.sell_orders:
            return []

        best_bid = max(depth.buy_orders.keys())
        best_ask = min(depth.sell_orders.keys())
        if best_bid >= best_ask:
            return []

        spread = best_ask - best_bid
        if spread < 2 or spread > self.MAKER_MAX_SPREAD.get(product, 1_000_000):
            return []

        fair = self.passive_fair(product, mid, under_mid)
        if fair is None:
            return []

        edge = self.MAKER_EDGE.get(product, 1.0)
        base_qty = self.MAKER_QTY.get(product, 6)
        full_pos = int(limit * self.FULL_INV_FRAC)

        bid_px = best_bid + 1 if spread >= 3 else best_bid
        ask_px = best_ask - 1 if spread >= 3 else best_ask
        if bid_px >= ask_px:
            bid_px = best_bid
            ask_px = best_ask
            if bid_px >= ask_px:
                return []

        buy_ok = (bid_px <= fair - edge) or (position <= -full_pos and bid_px <= fair + edge)
        sell_ok = (ask_px >= fair + edge) or (position >= full_pos and ask_px >= fair - edge)

        orders: List[Order] = []
        pos = position

        if buy_ok and buy_room > 0 and pos < limit:
            if position <= -full_pos:
                qty = min(buy_room, limit - pos, max(base_qty, min(40, -position)))
            else:
                qty = min(buy_room, limit - pos, base_qty)
            if qty > 0:
                orders.append(Order(product, int(bid_px), int(qty)))
                pos += qty

        if sell_ok and sell_room > 0 and pos > -limit:
            if position >= full_pos:
                qty = min(sell_room, pos + limit, max(base_qty, min(40, position)))
            else:
                qty = min(sell_room, pos + limit, base_qty)
            if qty > 0:
                orders.append(Order(product, int(ask_px), -int(qty)))

        return orders

    def zero_cost_voucher_orders(self, product: str, position: int, limit: int) -> List[Order]:
        orders: List[Order] = []
        if position < limit:
            orders.append(Order(product, 0, int(min(self.ZERO_BID_QTY, limit - position))))
        if position > 0:
            orders.append(Order(product, 1, -int(min(self.ZERO_BID_QTY, position))))
        return orders

    def active_maps(self):
        return self.BASE_BUY, self.BASE_SELL, self.BASE_HYBRID_BUY, self.BASE_HYBRID_SELL

    def apply_voucher_crash_cooldown(
        self,
        product: str,
        position: int,
        buy_room: int,
        sell_room: int,
        underlying_trend: float,
    ):
        if product not in self.VOUCHERS:
            return buy_room, sell_room

        if underlying_trend <= -self.VOUCHER_CRASH_TREND:
            self.voucher_crash_cooldown[product] = self.VOUCHER_CRASH_COOLDOWN_TICKS

        if self.voucher_crash_cooldown[product] <= 0:
            return buy_room, sell_room

        self.voucher_crash_cooldown[product] -= 1

        if position > 0:
            buy_room = 0
            sell_room = min(sell_room, position)
        elif position < 0:
            buy_room = min(buy_room, -position)
            sell_room = 0
        else:
            buy_room = 0
            sell_room = 0

        return buy_room, sell_room

    def safety_take_edges(
        self,
        product: str,
        depth: OrderDepth,
        buy_threshold: float,
        sell_threshold: float,
        position: int,
        limit: int,
        buy_room: int,
        sell_room: int,
    ) -> List[Order]:
        orders: List[Order] = []
        pos = position
        max_take = self.HYDROGEL_MAX_TAKE if product == "HYDROGEL_PACK" else None
        bought = 0
        sold = 0

        if buy_room > 0:
            for ask_price, ask_volume in sorted(depth.sell_orders.items()):
                available = -ask_volume
                if available <= 0:
                    continue

                if max_take is not None and bought >= max_take:
                    break

                if ask_price <= buy_threshold:
                    qty_cap = max_take - bought if max_take is not None else available
                    qty = min(available, buy_room, limit - pos, qty_cap)
                    if qty > 0:
                        orders.append(Order(product, int(ask_price), int(qty)))
                        pos += qty
                        buy_room -= qty
                        bought += qty
                else:
                    break

        if sell_room > 0:
            for bid_price, bid_volume in sorted(depth.buy_orders.items(), reverse=True):
                available = bid_volume
                if available <= 0:
                    continue

                if max_take is not None and sold >= max_take:
                    break

                if bid_price >= sell_threshold:
                    qty_cap = max_take - sold if max_take is not None else available
                    qty = min(available, sell_room, pos + limit, qty_cap)
                    if qty > 0:
                        orders.append(Order(product, int(bid_price), -int(qty)))
                        pos -= qty
                        sell_room -= qty
                        sold += qty
                else:
                    break

        return orders

    def hybrid_guarded_thresholds(
        self,
        product: str,
        base_buy: float,
        base_sell: float,
        under_mid: Optional[float],
    ):
        fair = self.option_fair(product, under_mid)
        if fair is None:
            return base_buy, base_sell

        guard = self.HYBRID_FAIR_GUARD[product]
        return min(base_buy, fair + guard), max(base_sell, fair - guard)

    def risk_rooms(
        self,
        product: str,
        depth: OrderDepth,
        position: int,
        limit: int,
    ):
        buy_room = limit - position
        sell_room = position + limit

        best_bid = max(depth.buy_orders.keys())
        best_ask = min(depth.sell_orders.keys())
        if best_bid >= best_ask:
            return max(0, -position), max(0, position)

        spread = best_ask - best_bid
        max_spread = self.RISK_MAX_SPREAD.get(product)
        if max_spread is not None and spread > max_spread:
            return max(0, -position), max(0, position)

        bid_volume, ask_volume = self.visible_volume(depth)
        min_visible = self.RISK_MIN_VISIBLE.get(product)
        if min_visible is not None and (bid_volume < min_visible or ask_volume < min_visible):
            return max(0, -position), max(0, position)

        hist = self.mid_history[product]
        max_tick_move = self.RISK_MAX_TICK_MOVE.get(product)
        if max_tick_move is not None and len(hist) >= 2:
            one_tick_move = abs(hist[-1] - hist[-2])
            if one_tick_move > max_tick_move:
                self.risk_cooldown[product] = self.RISK_COOLDOWN_TICKS

        if self.risk_cooldown[product] > 0:
            self.risk_cooldown[product] -= 1
            return max(0, -position), max(0, position)

        return max(0, buy_room), max(0, sell_room)

    def thresholds(
        self,
        product: str,
        buy_map: Dict[str, float],
        sell_map: Dict[str, float],
        hybrid_buy_map: Dict[str, float],
        hybrid_sell_map: Dict[str, float],
        under_mid: Optional[float],
    ):
        if product == "HYDROGEL_PACK":
            return self.HYDROGEL_BUY_TH, self.HYDROGEL_SELL_TH

        if product == "VELVETFRUIT_EXTRACT":
            return hybrid_buy_map[product], hybrid_sell_map[product]

        if product in ("VEV_4500", "VEV_5000"):
            return self.hybrid_guarded_thresholds(
                product=product,
                base_buy=hybrid_buy_map[product],
                base_sell=hybrid_sell_map[product],
                under_mid=under_mid,
            )

        return buy_map[product], sell_map[product]

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}

        self.update_mid_history(state)
        self.update_hydrogel_flow(state)

        buy_map, sell_map, hybrid_buy, hybrid_sell = self.active_maps()
        underlying_trend = self.get_underlying_trend()
        under_mid = self.synthetic_under_mid(state)

        for product in buy_map:
            depth = state.order_depths.get(product)
            if depth is None:
                continue

            position = state.position.get(product, 0)
            limit = self.LIMITS[product]
            mid = self.mid_from_depth(depth)
            if mid is None:
                continue

            buy_room, sell_room = self.risk_rooms(
                product=product,
                depth=depth,
                position=position,
                limit=limit,
            )

            buy_room, sell_room = self.apply_voucher_crash_cooldown(
                product=product,
                position=position,
                buy_room=buy_room,
                sell_room=sell_room,
                underlying_trend=underlying_trend,
            )

            if buy_room <= 0 and sell_room <= 0:
                continue

            buy_th, sell_th = self.thresholds(
                product=product,
                buy_map=buy_map,
                sell_map=sell_map,
                hybrid_buy_map=hybrid_buy,
                hybrid_sell_map=hybrid_sell,
                under_mid=under_mid,
            )

            if product == "HYDROGEL_PACK":
                skew = self.hydrogel_flow_skew()
                buy_th += skew
                sell_th += skew

            shift = self.imbalance_threshold_shift(product, depth)
            buy_th += shift
            sell_th += shift

            orders = self.safety_take_edges(
                product=product,
                depth=depth,
                buy_threshold=buy_th,
                sell_threshold=sell_th,
                position=position,
                limit=limit,
                buy_room=max(0, buy_room),
                sell_room=max(0, sell_room),
            )

            if product == "HYDROGEL_PACK":
                post_take_position = position + sum(order.quantity for order in orders)
                remaining_buy_room = min(max(0, buy_room), max(0, limit - post_take_position))
                remaining_sell_room = min(max(0, sell_room), max(0, limit + post_take_position))

                passive_orders = self.hydrogel_passive_quotes(
                    depth=depth,
                    position=post_take_position,
                    limit=limit,
                    buy_room=remaining_buy_room,
                    sell_room=remaining_sell_room,
                    buy_edge=buy_th,
                    sell_edge=sell_th,
                )
                if passive_orders:
                    orders.extend(passive_orders)
            elif not orders:
                orders = self.passive_edge_orders(
                    product=product,
                    depth=depth,
                    position=position,
                    limit=limit,
                    buy_room=max(0, buy_room),
                    sell_room=max(0, sell_room),
                    mid=mid,
                    under_mid=under_mid,
                )

            if orders:
                result[product] = orders

        for product in self.ZERO_BID_PRODUCTS:
            depth = state.order_depths.get(product)
            if depth is None:
                continue
            position = state.position.get(product, 0)
            orders = self.zero_cost_voucher_orders(product, position, self.LIMITS[product])
            if orders:
                result.setdefault(product, []).extend(orders)

        return result, 0, ""
