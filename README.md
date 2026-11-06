# NeuroTrade AI

**Self-Learning AI Trading System for Forex (XAUUSD Focus)**

> Personal use only. Not for commercial distribution.

## Overview

NeuroTrade AI is a local desktop application that:
- Connects to MetaTrader 5 (Demo account)
- Displays live candlestick charts (XAUUSD default)
- Analyzes market data using technical indicators
- Generates trading signals (Market/Limit orders)
- Executes testing trades on demo account
- Learns from trade results (adaptive weighted scoring)

## Tech Stack

- **Language:** Python 3.x
- **GUI:** PyQt6
- **Broker:** MetaTrader 5
- **Database:** SQLite
- **OS:** Windows 11

## Features

- [x] MT5 Connection
- [ ] Main Window UI
- [ ] Live Chart Viewer
- [ ] Data Engine
- [ ] AI Brain (Decision Making)
- [ ] Trade Executor (Demo)
- [ ] Feedback Loop
- [ ] Performance Dashboard
- [ ] Signal System + Copy
- [ ] Final Integration

## Installation

```bash
# Clone repository
git clone https://github.com/yohan0223/NeuroTradeAI

# Navigate to folder
cd NeuroTradeAI

# Create virtual environment
python -m venv .venv

# Activate virtual environment (Windows)
.\.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt