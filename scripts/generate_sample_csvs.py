"""
Synthetic Multi-Timeframe Sample CSV & SQLite Seeder for NeuroTrade AI.

Generates physically aligned 1H (400 bars), 15m (1600 bars), and 5m (4800 bars)
candle series spanning 180 hours of post-warmup evaluation data across Asian, London,
London-NY Overlap, and Rollover sessions.

Contains 6 to 8 distinct multi-timeframe setups across all 4 walk-forward folds:
- Prime London / Overlap hours: tight spread (1.0 pt), clean follow-through to TP1 / TP2
- Asian hours (00:00-07:00 UTC): 3-bar breakouts that fail unless filtered by Stage 2
- Rollover hours (21:00-23:00 UTC): wide-spread spikes filtered by Stage 2 & Stage 3
- 50/50 scale-outs and breakeven exits demonstrating Stage 5 edge preservation.

Supports exporting to CSV files in data/samples/ and seeding into SQLite CandleStore & WeightStore.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import DB_PATH
from core.data_store import CandleStore
from core.weight_store import WeightStore


def generate_synthetic_dataset(
    output_dir: str = "data/samples",
    start_time: str = "2026-04-01 00:00:00",
    h1_bars: int = 400,
    seed: int = 42,
    seed_sqlite: bool = False,
    db_path: Optional[str] = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Generate causally aligned 1H, 15m, and 5m OHLCV datasets with multi-session setups.
    Optionally upserts into SQLite CandleStore and saves XAUUSD contract in WeightStore.
    """
    os.makedirs(output_dir, exist_ok=True)
    rng = np.random.default_rng(seed)

    total_m5 = h1_bars * 12  # 12 M5 bars per hour = 4,800 bars
    start_dt = pd.to_datetime(start_time)
    times = [start_dt + timedelta(minutes=5 * i) for i in range(total_m5)]

    # 1. Warmup period (bars 0 to 2640 = 220 H1 bars) for EMA200 / EMA50 indicator warmup
    warmup_m5 = 2640
    prices = np.zeros(total_m5)
    prices[:warmup_m5] = (
        np.linspace(2150.0, 2300.0, warmup_m5)
        + 0.5 * np.sin(np.arange(warmup_m5) / 10.0)
    )

    # 2. Evaluation period: gentle random walk establishing macro uptrend (close > EMA50 > EMA200)
    steps = rng.normal(0.004, 0.04, total_m5)
    prices[warmup_m5:] = 2300.0 + np.cumsum(steps[warmup_m5:])

    spreads = np.zeros(total_m5)
    for i in range(total_m5):
        h = times[i].hour
        if 21 <= h <= 23:
            spreads[i] = 25.0  # Rollover spread: 25 pts (0.25), blocks via spread gate
        elif 8 <= h <= 16:
            spreads[i] = 1.0   # Prime spread: 1 pt (0.01), passes spread gate
        else:
            spreads[i] = 2.0   # Asian spread: 2 pts (0.02)

    # Explicit setup injection moments across all 4 walk-forward folds:
    # Fold 1: bars 2640 to 3180
    # Fold 2: bars 3180 to 3720
    # Fold 3: bars 3720 to 4260
    # Fold 4: bars 4260 to 4800
    setups = [
        # (bar_idx, type)
        (2760, "asian_breakout"),  # Fold 1: 06:00 UTC (Asian)
        (2840, "prime_winner"),    # Fold 1: 12:40 UTC (Prime Overlap)
        (3220, "prime_winner"),    # Fold 2: 08:20 UTC (Prime London)
        (3380, "rollover_spike"),  # Fold 2: 21:40 UTC (Rollover)
        (3780, "asian_breakout"),  # Fold 3: 03:00 UTC (Asian)
        (3900, "prime_retrace"),   # Fold 3: 13:00 UTC (Prime Overlap)
        (4340, "prime_winner"),    # Fold 4: 10:00 UTC (Prime London)
        (4480, "rollover_spike"),  # Fold 4: 21:40 UTC (Rollover)
    ]

    for idx, stype in setups:
        p_base = prices[idx - 5]
        for k in range(4):
            prices[idx - 4 + k] = p_base + k * 0.02

        prior_high = max(prices[idx - 4:idx])
        trigger_p = prior_high + 0.06
        prices[idx] = trigger_p

        if stype == "asian_breakout":
            spreads[idx] = 2.0
            # Fails: drops 2.50 points over 8 bars hitting SL
            for post in range(1, 15):
                prices[idx + post] = trigger_p - post * 0.20

        elif stype == "rollover_spike":
            spreads[idx] = 25.0  # Wide spread: 25 pts = 0.25
            # Fails: chops and drops 2.50 points hitting SL
            for post in range(1, 15):
                prices[idx + post] = trigger_p - post * 0.20

        elif stype == "prime_winner":
            spreads[idx] = 1.0  # Tight spread: 1 pt = 0.01
            # Wins: rises +3.50 points hitting TP1 (+1.5R) and TP2 (+2.0R)
            for post in range(1, 20):
                prices[idx + post] = trigger_p + min(3.5, post * 0.25)
            for post in range(20, 40):
                prices[idx + post] = trigger_p + 3.5 + rng.normal(0, 0.02)

        elif stype == "prime_retrace":
            spreads[idx] = 1.0
            # Hits TP1 (+0.25 pts) at post 6, then retraces back to entry at post 14
            for post in range(1, 7):
                prices[idx + post] = trigger_p + post * 0.05
            for post in range(7, 20):
                prices[idx + post] = (trigger_p + 0.30) - (post - 6) * 0.04

    # Build M5 candle records
    m5_records = []
    for i in range(total_m5):
        t = times[i]
        cp = round(float(prices[i]), 2)
        op = round(float(prices[i - 1]), 2) if i > 0 else cp
        sp = float(spreads[i])
        hp = round(max(op, cp) + 0.05, 2)
        lp = round(min(op, cp) - 0.05, 2)
        m5_records.append({
            "time": t.strftime("%Y-%m-%d %H:%M:%S"),
            "open": op,
            "high": hp,
            "low": lp,
            "close": cp,
            "tick_volume": 120,
            "spread": sp,
        })
    df_m5 = pd.DataFrame(m5_records)

    # Aggregate into physically aligned M15 candles (every 3 bars)
    m15_records = []
    for i in range(0, total_m5, 3):
        group = df_m5.iloc[i : i + 3]
        if len(group) == 3:
            op = group.iloc[0]["open"]
            cp = group.iloc[-1]["close"]
            hp = max(group["high"].max(), op, cp)
            lp = min(group["low"].min(), op, cp)
            m15_records.append({
                "time": group.iloc[0]["time"],
                "open": op,
                "high": hp,
                "low": lp,
                "close": cp,
                "tick_volume": int(group["tick_volume"].sum()),
                "spread": float(group["spread"].median()),
            })
    df_m15 = pd.DataFrame(m15_records)

    # Aggregate into physically aligned 1H candles (every 12 bars)
    h1_records = []
    for i in range(0, total_m5, 12):
        group = df_m5.iloc[i : i + 12]
        if len(group) == 12:
            op = group.iloc[0]["open"]
            cp = group.iloc[-1]["close"]
            hp = max(group["high"].max(), op, cp)
            lp = min(group["low"].min(), op, cp)
            h1_records.append({
                "time": group.iloc[0]["time"],
                "open": op,
                "high": hp,
                "low": lp,
                "close": cp,
                "tick_volume": int(group["tick_volume"].sum()),
                "spread": float(group["spread"].median()),
            })
    df_h1 = pd.DataFrame(h1_records)

    # Save to CSV files
    m5_path = os.path.join(output_dir, "synthetic_xauusd_5m.csv")
    m15_path = os.path.join(output_dir, "synthetic_xauusd_15m.csv")
    h1_path = os.path.join(output_dir, "synthetic_xauusd_1H.csv")

    df_m5.to_csv(m5_path, index=False)
    df_m15.to_csv(m15_path, index=False)
    df_h1.to_csv(h1_path, index=False)

    print("=" * 80)
    print("NEUROTRADE AI SYNTHETIC DATASET GENERATION COMPLETE")
    print("=" * 80)
    print(f"Output directory : {os.path.abspath(output_dir)}")
    print(f"Date range       : {df_h1.iloc[0]['time']} to {df_h1.iloc[-1]['time']}")
    print(f"1H Candles       : {len(df_h1):>5} bars -> {h1_path}")
    print(f"15m Candles      : {len(df_m15):>5} bars -> {m15_path}")
    print(f"5m Candles       : {len(df_m5):>5} bars -> {m5_path}")
    print("=" * 80)

    # Upsert to SQLite if requested
    if seed_sqlite:
        target_db = db_path or DB_PATH
        print(f"\nSeeding SQLite database at: {os.path.abspath(target_db)} ...")

        store = CandleStore(db_path=target_db)
        if not store.connect():
            raise RuntimeError(f"Could not connect to CandleStore at {target_db}")

        wstore = WeightStore(db_path=target_db)
        if not wstore.connect():
            raise RuntimeError(f"Could not connect to WeightStore at {target_db}")

        try:
            w_h1 = store.upsert_candles("XAUUSD", "1H", df_h1)
            w_m15 = store.upsert_candles("XAUUSD", "15m", df_m15)
            w_m5 = store.upsert_candles("XAUUSD", "5m", df_m5)
            print(f"  [OK] CandleStore: 1H={w_h1}, 15m={w_m15}, 5m={w_m5} candles upserted.")

            wstore.save_contract(
                symbol="XAUUSD",
                resolved_symbol="XAUUSD",
                point=0.01,
                digits=2,
            )
            print("  [OK] WeightStore: Saved contract info for XAUUSD (point=0.01, digits=2).")
            print("SQLite offline seeding completed successfully.")
        finally:
            store.close()
            wstore.close()

    return df_h1, df_m15, df_m5


def parse_args():
    parser = argparse.ArgumentParser(
        description="Synthetic Multi-Timeframe Sample CSV & SQLite Seeder for NeuroTrade AI."
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/samples",
        help="Directory to save generated CSV files (default: data/samples).",
    )
    parser.add_argument(
        "--start-time",
        type=str,
        default="2026-04-01 00:00:00",
        help="Starting datetime string (default: '2026-04-01 00:00:00').",
    )
    parser.add_argument(
        "--h1-bars",
        type=int,
        default=400,
        help="Number of 1H bars to generate (default: 400 = 4,800 M5 bars).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for repeatable data generation (default: 42).",
    )
    parser.add_argument(
        "--seed-sqlite",
        action="store_true",
        help="Upsert generated candles into CandleStore (neurotrade.db) and save XAUUSD contract in WeightStore.",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Optional custom SQLite database path (defaults to config.DB_PATH).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    cli_args = parse_args()
    generate_synthetic_dataset(
        output_dir=cli_args.output_dir,
        start_time=cli_args.start_time,
        h1_bars=cli_args.h1_bars,
        seed=cli_args.seed,
        seed_sqlite=cli_args.seed_sqlite,
        db_path=cli_args.db_path,
    )
