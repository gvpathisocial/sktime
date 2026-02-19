import pandas as pd

from sktime_quant.execution.orders import OrderExporter



def test_order_exporter_generates_and_sorts_orders(tmp_path):
    allocation = pd.DataFrame(
        {
            "asset": ["B", "A"],
            "target_weight": [0.5, 0.5],
            "confidence": [0.97, 0.96],
        }
    )
    prices = pd.DataFrame({"asset": ["A", "B"], "close": [100.0, 200.0]})
    orders = OrderExporter().generate_orders(allocation, prices, "2026-01-01")
    assert list(orders["asset"]) == sorted(list(orders["asset"]))

    out_path = tmp_path / "orders.csv"
    written = OrderExporter().to_csv(orders, out_path)
    assert out_path.exists()
    assert str(out_path) == written


def test_order_exporter_respects_no_trade_band_and_min_notional():
    allocation = pd.DataFrame(
        {
            "asset": ["A", "B"],
            "target_weight": [0.5005, 0.001],
            "confidence": [0.97, 0.96],
        }
    )
    prices = pd.DataFrame({"asset": ["A", "B"], "close": [100.0, 100.0]})
    current = pd.Series({"A": 5000, "B": 0})

    orders = OrderExporter().generate_orders(
        allocation_frame=allocation,
        price_frame=prices,
        as_of_date="2026-01-01",
        current_positions=current,
        portfolio_value=1000000.0,
        no_trade_band=0.001,
        min_order_notional=2000.0,
    )
    assert orders.empty


def test_order_exporter_applies_lot_size_constraints():
    allocation = pd.DataFrame(
        {
            "asset": ["A", "B"],
            "target_weight": [0.253, 0.121],
            "confidence": [0.97, 0.96],
        }
    )
    prices = pd.DataFrame({"asset": ["A", "B"], "close": [10.0, 20.0]})
    current = pd.Series({"A": 0, "B": 0})

    orders = OrderExporter().generate_orders(
        allocation_frame=allocation,
        price_frame=prices,
        as_of_date="2026-01-01",
        current_positions=current,
        portfolio_value=10000.0,
        default_lot_size=25,
        lot_size_by_asset={"B": 40},
    )
    qty_a = int(orders.loc[orders["asset"] == "A", "quantity"].iloc[0])
    qty_b = int(orders.loc[orders["asset"] == "B", "quantity"].iloc[0])
    assert qty_a % 25 == 0
    assert qty_b % 40 == 0


def test_order_exporter_diagnostics_for_notional_caps():
    allocation = pd.DataFrame(
        {
            "asset": ["A", "B"],
            "target_weight": [0.8, 0.4],
            "confidence": [0.99, 0.99],
        }
    )
    prices = pd.DataFrame({"asset": ["A", "B"], "close": [100.0, 100.0]})

    orders, diagnostics = OrderExporter().generate_orders_with_diagnostics(
        allocation_frame=allocation,
        price_frame=prices,
        as_of_date="2026-01-01",
        portfolio_value=100000.0,
        max_order_notional=30000.0,
        max_turnover_notional_per_asset=20000.0,
    )
    assert orders.empty
    drops = diagnostics["dropped_reason_counts"]
    assert drops["exceeds_max_order_notional"] >= 1 or drops["exceeds_turnover_per_asset_cap"] >= 1

