"""
Synthetic Multi-Timeframe Sample CSV Generator for NeuroTrade AI.

Generates physically aligned 1H, 15m, and 5m candle CSVs spanning ~12 days of
market data (280 H1 bars, 1120 M15 bars, 3360 M5 bars) with realistic trend waves
and session structure across Asian, London, London-NY Overlap, and Rollover sessions.
Strictly used for offline verification of the CLI Backtester, Ablation Study, and Walk-Forward Validator.
Does not write to SQLite or modify any databases.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
import numpy as np
import pandas as pd


def generate_synthetic_dataset(
    output_dir: str = "data/samples",
    start_time: str = "2026-04-01 00:00:00",
    h1_bars: int = 280,
    seed: int = 42,
) -> None:
    """
    Generate causally aligned 1H, 15m, and 5m OHLCV CSV files with natural
    trend structure and pullbacks to trigger valid intraday setups.
    """
    os.makedirs(output_dir, exist_ok=True)
    rng = np.random.RandomState(seed)

    total_m5_bars = h1_bars * 12  # 12 M5 bars per hour = 3360 bars
    start_dt = pd.to_datetime(start_time)
    times = [start_dt + timedelta(minutes=5 * i) for i in range(total_m5_bars)]

    # Multi-frequency wave with gentle upward drift to form causal EMA 9 > 21 > 50 > 200 alignment
    # plus periodic pullbacks to test intraday EMA 21 pullbacks
    x = np.arange(total_m5_bars, dtype=float)
    trend_drift = 0.035 * x
    macro_cycle = 4.5 * np.sin(x / 240.0)
    intraday_cycle = 1.2 * np.sin(x / 36.0) + 0.6 * np.cos(x / 18.0)
    micro_noise = rng.normal(0, 0.15, total_m5_bars)

    base_prices = 2300.0 + trend_drift + macro_cycle + intraday_cycle + micro_noise

    m5_records = []
    for i in range(total_m5_bars):
        t = times[i]
        hour = t.hour
        close_p = round(float(base_prices[i]), 2)
        open_p = round(float(base_prices[i - 1]), 2) if i > 0 else close_p

        # Session-aware spread modeling
        if 21 <= hour <= 23:
            spread_val = 35.0  # Rollover spread widening
        elif 12 <= hour <= 16:
            spread_val = 14.0  # London-NY overlap tight spread
        elif 7 <= hour < 12:
            spread_val = 16.0  # London session
        else:
            spread_val = 22.0  # Asian session

        high_ext = abs(rng.normal(0.35, 0.15))
        low_ext = abs(rng.normal(0.35, 0.15))
        high_p = round(max(open_p, close_p) + high_ext, 2)
        low_p = round(min(open_p, close_p) - low_ext, 2)
        vol_val = int(abs(rng.normal(120, 30))) + 20

        m5_records.append({
            "time": t.strftime("%Y-%m-%d %H:%M:%S"),
            "open": open_p,
            "high": high_p,
            "low": low_p,
            "close": close_p,
            "tick_volume": vol_val,
            "spread": spread_val,
        })

    df_m5 = pd.DataFrame(m5_records)

    # Aggregate into physically aligned M15 candles (every 3 bars)
    m15_records = []
    for i in range(0, total_m5_bars, 3):
        group = df_m5.iloc[i : i + 3]
        if group.empty:
            continue
        m15_records.append({
            "time": group.iloc[0]["time"],
            "open": group.iloc[0]["open"],
            "high": group["high"].max(),
            "low": group["low"].min(),
            "close": group.iloc[-1]["close"],
            "tick_volume": int(group["tick_volume"].sum()),
            "spread": float(group["spread"].median()),
        })
    df_m15 = pd.DataFrame(m15_records)

    # Aggregate into physically aligned 1H candles (every 12 bars)
    h1_records = []
    for i in range(0, total_m5_bars, 12):
        group = df_m5.iloc[i : i + 12]
        if group.empty:
            continue
        h1_records.append({
            "time": group.iloc[0]["time"],
            "open": group.iloc[0]["open"],
            "high": group["high"].max(),
            "low": group["low"].min(),
            "close": group.iloc[-1]["close"],
            "tick_volume": int(group["tick_volume"].sum()),
            "spread": float(group["spread"].median()),
        })
    df_h1 = pd.DataFrame(h1_records)

    # Write CSVs
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


if __name__ == "__main__":
    generate_synthetic_dataset()
