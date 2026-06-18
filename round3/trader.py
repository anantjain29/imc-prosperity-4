from datamodel import OrderDepth, TradingState, Order
from typing import Dict, List, Optional


class Trader:

    LIMITS = {
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
    }

    # Final crossing bands.
    BUY_TH = {
        "HYDROGEL_PACK": 9946,
        "VELVETFRUIT_EXTRACT": 5245,
        "VEV_4000": 1231,
        "VEV_4500": 728,
        "VEV_5000": 238,
        "VEV_5200": 86,
        "VEV_5300": 41,
        "VEV_5400": 12,
        "VEV_5500": 3,
    }

    SELL_TH = {
        "HYDROGEL_PACK": 10019,
        "VELVETFRUIT_EXTRACT": 5272,
        "VEV_4000": 1264,
        "VEV_4500": 767,
        "VEV_5000": 274,
        "VEV_5200": 99,
        "VEV_5300": 48,
        "VEV_5400": 15,
        "VEV_5500": 5,
    }

    # Voucher fair = a + b * (underlying_mid - 5250).
    VOUCHER_MODEL = {
        "VEV_4000": (1250.005, 1.0000),
        "VEV_4500": (750.015, 1.0000),
        "VEV_5000": (251.85, 0.968),
        "VEV_5200": (86.25, 0.691),
        "VEV_5300": (38.79, 0.413),
        "VEV_5400": (9.73, 0.177),
        "VEV_5500": (3.21, 0.060),
    }

    # Fair-value caps keep threshold trades near the live option surface.
    FAIR_GUARD = {
        "VEV_4000": 20.0,
        "VEV_4500": 20.0,
        "VEV_5000": 20.0,
        "VEV_5200": 20.0,
        "VEV_5300": 15.0,
        "VEV_5400": 10.0,
        "VEV_5500": 5.0,
    }

    UNDER_REGIME_LOW = 5200.0
    UNDER_REGIME_HIGH = 5305.0

    # VEV_5100 uses its own relative-value fit.
    S0 = 5259.0
    V5100_BASE = 168.0
    V5100_DELTA = 0.50
    V5100_WIDTH = 2.0

    def mid(self, depth: Optional[OrderDepth]) -> Optional[float]:
        if depth is None or not depth.buy_orders or not depth.sell_orders:
            return None
        return (max(depth.buy_orders.keys()) + min(depth.sell_orders.keys())) / 2.0

    def take_edges(
        self,
        product: str,
        depth: OrderDepth,
        buy_threshold: float,
        sell_threshold: float,
        position: int,
        limit: int,
    ) -> List[Order]:
        orders: List[Order] = []
        pos = position

        for ask_price, ask_volume in sorted(depth.sell_orders.items()):
            available = -ask_volume
            if available <= 0:
                continue
            if ask_price <= buy_threshold and pos < limit:
                qty = min(available, limit - pos)
                if qty > 0:
                    orders.append(Order(product, ask_price, qty))
                    pos += qty
            else:
                break

        for bid_price, bid_volume in sorted(depth.buy_orders.items(), reverse=True):
            available = bid_volume
            if available <= 0:
                continue
            if bid_price >= sell_threshold and pos > -limit:
                qty = min(available, pos + limit)
                if qty > 0:
                    orders.append(Order(product, bid_price, -qty))
                    pos -= qty
            else:
                break

        return orders

    def guarded_thresholds(self, product: str, base_buy: float, base_sell: float, under_mid: Optional[float]):
        if under_mid is None or product not in self.VOUCHER_MODEL:
            return base_buy, base_sell

        a, b = self.VOUCHER_MODEL[product]
        fair = a + b * (under_mid - 5250.0)
        guard = self.FAIR_GUARD[product]

        buy_threshold = min(base_buy, fair + guard)
        sell_threshold = max(base_sell, fair - guard)

        # Outside the fitted range, cut risk on the side most exposed to drift.
        if under_mid > self.UNDER_REGIME_HIGH:
            sell_threshold = max(sell_threshold, fair - guard / 2.0)
        elif under_mid < self.UNDER_REGIME_LOW:
            buy_threshold = min(buy_threshold, fair + guard / 2.0)

        return buy_threshold, sell_threshold

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}

        under_depth = state.order_depths.get("VELVETFRUIT_EXTRACT")
        under_mid = self.mid(under_depth)

        for product in ("HYDROGEL_PACK", "VELVETFRUIT_EXTRACT"):
            depth = state.order_depths.get(product)
            if depth is None:
                continue

            buy_th = self.BUY_TH[product]
            sell_th = self.SELL_TH[product]

            if product == "VELVETFRUIT_EXTRACT" and under_mid is not None:
                if under_mid > self.UNDER_REGIME_HIGH:
                    sell_th = max(sell_th, under_mid + 3.0)
                elif under_mid < self.UNDER_REGIME_LOW:
                    buy_th = min(buy_th, under_mid - 3.0)

            orders = self.take_edges(
                product, depth, buy_th, sell_th,
                state.position.get(product, 0), self.LIMITS[product]
            )
            if orders:
                result[product] = orders

        for product in ("VEV_4000", "VEV_4500", "VEV_5000", "VEV_5200", "VEV_5300", "VEV_5400", "VEV_5500"):
            depth = state.order_depths.get(product)
            if depth is None:
                continue

            buy_th, sell_th = self.guarded_thresholds(
                product, self.BUY_TH[product], self.SELL_TH[product], under_mid
            )

            orders = self.take_edges(
                product, depth, buy_th, sell_th,
                state.position.get(product, 0), self.LIMITS[product]
            )
            if orders:
                result[product] = orders

        opt_depth = state.order_depths.get("VEV_5100")
        if opt_depth is not None and under_mid is not None:
            fair = self.V5100_BASE + self.V5100_DELTA * (under_mid - self.S0)
            orders = self.take_edges(
                "VEV_5100", opt_depth,
                fair - self.V5100_WIDTH, fair + self.V5100_WIDTH,
                state.position.get("VEV_5100", 0), self.LIMITS["VEV_5100"]
            )
            if orders:
                result["VEV_5100"] = orders

        return result, 0, ""
