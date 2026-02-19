"""Daily offline broker order file creation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ORDER_COLUMNS = [
    "date",
    "asset",
    "side",
    "quantity",
    "order_type",
    "limit_price",
    "stop_price",
    "time_in_force",
    "strategy_id",
    "confidence",
    "target_weight",
]


class OrderExporter:
    @staticmethod
    def _empty_diagnostics() -> dict[str, object]:
        return {
            "executed_order_count": 0,
            "total_order_notional": 0.0,
            "dropped_reason_counts": {
                "no_price": 0,
                "no_trade_band": 0,
                "zero_delta": 0,
                "lot_round_to_zero": 0,
                "below_min_notional": 0,
                "exceeds_max_order_notional": 0,
                "exceeds_turnover_per_asset_cap": 0,
            },
        }

    def generate_orders_with_diagnostics(
        self,
        allocation_frame: pd.DataFrame,
        price_frame: pd.DataFrame,
        as_of_date: str,
        current_positions: pd.Series | None = None,
        portfolio_value: float = 1000000.0,
        strategy_id: str = "sktime_quant",
        no_trade_band: float = 0.0,
        min_order_notional: float = 0.0,
        default_lot_size: int = 1,
        lot_size_by_asset: dict[str, int] | None = None,
        max_order_notional: float = 0.0,
        max_turnover_notional_per_asset: float = 0.0,
    ) -> tuple[pd.DataFrame, dict[str, object]]:
        diagnostics = self._empty_diagnostics()
        dropped = diagnostics["dropped_reason_counts"]
        turnover_by_asset: dict[str, float] = {}

        if "asset" not in allocation_frame or "target_weight" not in allocation_frame:
            raise ValueError("allocation_frame must include asset and target_weight")
        if "asset" not in price_frame or "close" not in price_frame:
            raise ValueError("price_frame must include asset and close")

        current = current_positions if current_positions is not None else pd.Series(dtype=float)
        price = price_frame.drop_duplicates("asset").set_index("asset")["close"].astype(float)

        rows = []
        lot_map = lot_size_by_asset or {}
        for _, row in allocation_frame.iterrows():
            asset = str(row["asset"])
            px = float(price.get(asset, 0.0))
            if px <= 0:
                dropped["no_price"] += 1
                continue
            current_qty = int(current.get(asset, 0.0))
            current_weight = (current_qty * px) / portfolio_value if portfolio_value > 0 else 0.0
            target_weight = float(row["target_weight"])
            if abs(target_weight - current_weight) < no_trade_band:
                dropped["no_trade_band"] += 1
                continue
            target_qty = int((target_weight * portfolio_value) / px)
            delta = target_qty - current_qty
            if delta == 0:
                dropped["zero_delta"] += 1
                continue
            lot_size = int(lot_map.get(asset, default_lot_size))
            if lot_size <= 0:
                lot_size = 1
            rounded_qty = (abs(delta) // lot_size) * lot_size
            if rounded_qty == 0:
                dropped["lot_round_to_zero"] += 1
                continue

            order_notional = rounded_qty * px
            if min_order_notional > 0 and order_notional < min_order_notional:
                dropped["below_min_notional"] += 1
                continue
            if max_order_notional > 0 and order_notional > max_order_notional:
                dropped["exceeds_max_order_notional"] += 1
                continue

            cum = turnover_by_asset.get(asset, 0.0) + order_notional
            if max_turnover_notional_per_asset > 0 and cum > max_turnover_notional_per_asset:
                dropped["exceeds_turnover_per_asset_cap"] += 1
                continue
            turnover_by_asset[asset] = cum

            rows.append(
                {
                    "date": as_of_date,
                    "asset": asset,
                    "side": "BUY" if delta > 0 else "SELL",
                    "quantity": rounded_qty,
                    "order_type": "MKT",
                    "limit_price": "",
                    "stop_price": "",
                    "time_in_force": "DAY",
                    "strategy_id": strategy_id,
                    "confidence": float(row.get("confidence", 0.0)),
                    "target_weight": target_weight,
                }
            )

        orders = pd.DataFrame(rows, columns=ORDER_COLUMNS)
        orders = orders.sort_values(["asset", "side"]).reset_index(drop=True)
        diagnostics["executed_order_count"] = int(len(orders))
        diagnostics["total_order_notional"] = float(sum(turnover_by_asset.values()))
        return orders, diagnostics

    def generate_orders(
        self,
        allocation_frame: pd.DataFrame,
        price_frame: pd.DataFrame,
        as_of_date: str,
        current_positions: pd.Series | None = None,
        portfolio_value: float = 1000000.0,
        strategy_id: str = "sktime_quant",
        no_trade_band: float = 0.0,
        min_order_notional: float = 0.0,
        default_lot_size: int = 1,
        lot_size_by_asset: dict[str, int] | None = None,
        max_order_notional: float = 0.0,
        max_turnover_notional_per_asset: float = 0.0,
    ) -> pd.DataFrame:
        orders, _ = self.generate_orders_with_diagnostics(
            allocation_frame=allocation_frame,
            price_frame=price_frame,
            as_of_date=as_of_date,
            current_positions=current_positions,
            portfolio_value=portfolio_value,
            strategy_id=strategy_id,
            no_trade_band=no_trade_band,
            min_order_notional=min_order_notional,
            default_lot_size=default_lot_size,
            lot_size_by_asset=lot_size_by_asset,
            max_order_notional=max_order_notional,
            max_turnover_notional_per_asset=max_turnover_notional_per_asset,
        )
        return orders

    def to_csv(self, orders: pd.DataFrame, output_path: str | Path) -> str:
        missing = [c for c in ORDER_COLUMNS if c not in orders.columns]
        if missing:
            raise ValueError(f"orders missing required columns: {missing}")

        out = orders[ORDER_COLUMNS].copy()
        if out[["date", "asset", "side", "quantity", "order_type", "time_in_force"]].isna().any().any():
            raise ValueError("orders contain null values in required fields")

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(path, index=False)
        return str(path)

