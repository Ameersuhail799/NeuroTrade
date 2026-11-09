"""
Synthetic Multi-Timeframe Sample CSV Generator for NeuroTrade AI.

Generates physically aligned 1H (400 bars), 15m (1600 bars), and 5m (4800 bars)
candle CSVs spanning 180 hours of post-warmup evaluation data across Asian, London,
London-NY Overlap, and Rollover sessions.

Constructed with clear multi-day bullish and bearish H1 regimes, constructive M15 RSI/MACD,
and realistic M5 triggers:
- Prime London / Overlap hours: tight spread, clean follow-through to TP1 / TP2
- Asian hours (00:00-07:00 UTC): 3-bar breakouts that fail unless filtered by Stage 2
- Rollover hours (21:00-23:00 UTC): wide-spread spikes filtered by Stage 2 & Stage 3
- 50/50 scale-outs and breakeven exits demonstrating Stage 5 edge preservation.

Strictly used for offline verification of the CLI Backtester and Walk-Forward Validator.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
import numpy as np
import pandas as pd


def generate_synthetic_dataset(
    output_dir: str = "data/samples",
    start_time: str = "2026-04-01 00:00:00",
    h1_bars: int = 400,
    seed: int = 42,
) -> None:
    """
    Generate causally aligned 1H, 15m, and 5m OHLCV CSV files with multi-session setups.
    """
    os.makedirs(output_dir, exist_ok=True)
    rng = np.random.RandomState(seed)

    total_m5_bars = h1_bars * 12  # 12 M5 bars per hour = 4,800 bars
    start_dt = pd.to_datetime(start_time)
    times = [start_dt + timedelta(minutes=5 * i) for i in range(total_m5_bars)]

    warmup_m5 = 2640  # Exactly 220 H1 bars for indicator warmup
    prices = np.zeros(total_m5_bars)
    spreads = np.zeros(total_m5_bars)

    # 1. Warmup period (bars 0 to 2640): smooth ramp up establishing H1 EMA50 > EMA200
    prices[:warmup_m5] = (
        np.linspace(2150.0, 2350.0, warmup_m5)
        + 1.0 * np.sin(np.arange(warmup_m5) / 18.0)
    )
    spreads[:warmup_m5] = 16.0

    # 2. Evaluation period (bars 2640 to 4800 = 180 H1 bars = 7.5 days)
    # Split into Bullish regime (2640 to 3800) and Bearish regime (3800 to 4800)
    p = 2350.0

    for i in range(warmup_m5, total_m5_bars):
        t = times[i]
        hour = t.hour
        minute = t.minute

        # Set spread based on session
        if 21 <= hour <= 23:
            sp = 48.0  # Wide rollover spread
        elif 8 <= hour <= 16:
            sp = 14.0  # Tight prime session spread
        else:
            sp = 22.0  # Asian spread

        spreads[i] = sp

        if i < 3800:
            # === BULLISH MACRO REGIME ===
            if 8 <= hour <= 15:
                # Prime London / NY overlap: steady trend up with periodic consolidation
                if hour in (9, 13) and minute in (15, 20):
                    drift = 0.45  # M5 breakout bar
                    vol = 0.05
                elif hour in (11, 15):
                    drift = -0.02  # Pullback
                    vol = 0.10
                else:
                    drift = 0.06
                    vol = 0.18
            elif 21 <= hour <= 23:
                # Rollover: wide-spread spike that fails
                if hour == 21 and minute == 30:
                    drift = 0.50
                    vol = 0.05
                elif hour == 22:
                    drift = -0.20
                    vol = 0.10
                else:
                    drift = -0.01
                    vol = 0.08
            elif 0 <= hour <= 6:
                # Asian session: false breakout at 02:30 UTC that chops and fails
                if hour == 2 and minute == 30:
                    drift = 0.60  # Asian breakout trigger
                    vol = 0.05
                elif hour in (3, 4):
                    drift = -0.25  # Reversal hitting Asian stop loss
                    vol = 0.08
                else:
                    drift = -0.015
                    vol = 0.12
            else:
                drift = 0.02
                vol = 0.15

        else:
            # === BEARISH MACRO REGIME ===
            if 8 <= hour <= 15:
                # Prime London / NY overlap: steady trend down
                if hour in (9, 13) and minute in (15, 20):
                    drift = -0.45  # M5 breakdown bar
                    vol = 0.05
                elif hour in (11, 15):
                    drift = 0.02  # Pullback up
                    vol = 0.10
                else:
                    drift = -0.06
                    vol = 0.18
            elif 21 <= hour <= 23:
                # Rollover: wide-spread spike
                if hour == 21 and minute == 30:
                    drift = -0.50
                    vol = 0.05
                elif hour == 22:
                    drift = 0.20
                    vol = 0.10
                else:
                    drift = 0.01
                    vol = 0.08
            elif 0 <= hour <= 6:
                # Asian session: false breakdown that reverses
                if hour == 2 and minute == 30:
                    drift = -0.60
                    vol = 0.05
                elif hour in (3, 4):
                    drift = 0.25
                    vol = 0.08
                else:
                    drift = 0.015
                    vol = 0.12
            else:
                drift = -0.02
                vol = 0.15

        p += drift + rng.normal(0, vol)
        prices[i] = p

    # Build M5 candle records
    m5_records = []
    for i in range(total_m5_bars):
        t = times[i]
        cp = round(float(prices[i]), 2)
        op = round(float(prices[i - 1]), 2) if i > 0 else cp
        sp = float(spreads[i]) if spreads[i] > 0 else 20.0
        hp = round(max(op, cp) + abs(rng.normal(0.25, 0.08)), 2)
        lp = round(min(op, cp) - abs(rng.normal(0.25, 0.08)), 2)
        vol_val = int(abs(rng.normal(130, 30))) + 25

        m5_records.append({
            "time": t.strftime("%Y-%m-%d %H:%M:%S"),
            "open": op,
            "high": hp,
            "low": lp,
            "close": cp,
            "tick_volume": vol_val,
            "spread": sp,
        })

    df_m5 = pd.DataFrame(m5_records)

    # Physically aggregate into M15 candles (every 3 bars)
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

    # Physically aggregate into 1H candles (every 12 bars)
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


if __name__ == "__main__":
    generate_synthetic_dataset()
