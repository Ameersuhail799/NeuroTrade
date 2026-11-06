# NeuroTrade AI — Intraday Signal Engine (Research Baseline)

## Strategy layout

- **H1:** trend filter using close vs EMA 50 / EMA 200 plus EMA 50 slope.
- **M15:** setup filter using EMA 20 / EMA 50, RSI(14), and MACD histogram.
- **M5:** entry confirmation using a completed-candle 3-bar breakout or EMA 20 reclaim/rejection, momentum alignment, and an ATR extension filter.
- **Risk plan:** reference entry at the completed M5 close; stop based on the wider of the recent M5 swing and 1.5 x M15 ATR; targets at 1.5R and 2R. A stop wider than 3 x M15 ATR is rejected.

This is a deterministic rule-based baseline, not a trained ML model and not evidence of profitability. Confluence score is not win probability. No order execution is implemented in this module.

## Input requirements

Pass three chronological pandas DataFrames for the same broker-resolved symbol. Each needs `open`, `high`, `low`, `close`, and preferably `time`.

Recommended history sizes:

- H1: at least 221 rows fetched from MT5 (the final forming candle is excluded; 220 completed rows remain).
- M15: at least 61 rows.
- M5: at least 61 rows.

The engine excludes the last row by default because MT5 position 0 is typically the currently forming candle. Timeframe timestamps are checked for H1 <= M15 <= M5 ordering when all three frames contain `time`.

## Example call

```python
from core.intraday_signal_engine import IntradaySignalEngine

engine = IntradaySignalEngine()
signal = engine.generate_signal(
    h1=h1_candles,
    m15=m15_candles,
    m5=m5_candles,
    symbol=resolved_symbol,
    digits=mt5_symbol_info.digits,
    exclude_latest=True,
)

print(signal.to_dict())
```

`h1_candles`, `m15_candles`, and `m5_candles` must come from real source data. The unit tests use synthetic candles only to verify the code paths; those tests are not trading-performance results.

## Verification

From the project root with pandas and numpy installed:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q core tests
```

## Not implemented yet

- MT5 worker that fetches H1/M15/M5 in one operation.
- GUI panel integration and persistent signal history for this new signal format.
- Commission, spread, slippage, swap, and execution modelling.
- Position sizing by account risk and broker contract specifications.
- Historical event-driven backtesting and walk-forward validation.
- Evidence of positive expectancy or profitability.

Keep the app in demo-only mode. Do not route these signal candidates to the trade executor until the backtesting and risk controls are implemented and independently verified.
