# NeuroTrade AI - Project Context

## Purpose
A single-user, local-only desktop trading assistant for PERSONAL USE.
Not a commercial product. No multi-user, no accounts, no cloud backend.

## Environment
- OS: Windows 11
- Language: Python 3.x (64-bit)
- GUI: PyQt6
- Broker bridge: MetaTrader5 Python package
- Storage: SQLite (local)
- Editor: VS Code
- MT5 terminal installed and logged in to a DEMO account

## Non-Negotiable Rules
1. DEMO ONLY. Never send real-money orders. No live-trading toggle
   may be added without explicit user confirmation in a later phase.
2. Do NOT rewrite the whole project. Only create new files or modify
   the specific files required by the current part.
3. Before changing an existing file, read it first and preserve its
   public class names, method signatures and imports.
4. Implement ONLY the part numbered in the current request.
   Treat other prompt files as future reference, not as work to do now.
5. If a method cannot be fully implemented, mark it clearly as a stub
   with raise NotImplementedError and explain why. Never fake output.
6. Never invent MT5 connection results, prices, trade results or
   backtest statistics. All numbers must come from real data or be
   clearly labeled as sample/mock data.
7. All code, comments, variable names and UI text must be in English.
8. After each part, provide:
   - List of files created/changed
   - Full code for each new/changed file
   - Exact commands to run
   - A verification checklist
   - Known limitations

## Target
Primary symbol: XAUUSD (load this by default).
Also support: EURUSD, GBPUSD, USDJPY, AUDUSD.
Timeframes: 1m, 5m, 15m, 1H, 4H, 1D.

## Technical Constraints
- The MetaTrader5 Python package runs on Windows only and requires
  the MT5 terminal to be installed and running.
- Enable "Algo Trading" in the MT5 terminal for order execution.
- Broker symbol names may differ (XAUUSD, XAUUSD.a, GOLD).
  Resolve the symbol using mt5.symbols_get(), do not assume a name.
- Respect symbol rules: digits, volume_min, volume_max, volume_step,
  trade_stops_level. Round prices and volumes accordingly.
- All indicator math must be implemented with pandas/numpy only.
  Do not require TA-Lib (difficult to install on Windows).
- Keep network/database work off the GUI thread (QThread or QRunnable).

## Honesty Requirements for the AI Module
- Version 1 "self-learning" means adaptive weighted scoring with
  persisted weights, NOT a proven deep reinforcement learning agent.
- A "confidence %" is a heuristic score, NOT a calibrated win probability.
- Never promise profitability or a target accuracy percentage.
- Win rate alone is not success. Also track profit factor, expectancy,
  average win/loss, and maximum drawdown.
- Separate training data from out-of-sample validation data.
  Report out-of-sample results, not just in-sample results.
- Prevent look-ahead bias: signals may only use data available
  at the decision timestamp.

## Build Order
Part 1  -> Project setup + MT5 connection
Part 2  -> Main window shell
Part 3  -> Live candlestick chart
Part 4  -> Data engine + indicators
Part 5  -> Decision engine (rule-based first)
Part 6  -> Demo trade executor
Part 7  -> Feedback loop + weight adaptation
Part 8  -> Performance dashboard
Part 9  -> Signal panel + copy feature
Part 10 -> Integration + persistence + packaging

## Definition of Done
A part is finished only when it runs locally without errors and
its verification checklist passes.