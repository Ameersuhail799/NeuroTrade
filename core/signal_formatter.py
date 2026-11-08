"""
Formatting helpers for Part 9 and multi-timeframe signal history.

Produces readable text and JSON from real SignalRecord objects.
No order execution and no probability claims.
"""

import json

from core.signal_history import SignalRecord


class SignalFormatter:
    @staticmethod
    def to_text(record: SignalRecord) -> str:
        lines = []

        lines.append("NeuroTrade AI Signal Record")
        lines.append(f"Record ID: {record.record_id}")
        lines.append(f"Created at (local): {record.created_at}")
        lines.append(f"Engine: {record.engine} ({record.engine_version})")
        lines.append("")

        lines.append(
            f"Symbol: {record.symbol} | Timeframe: {record.timeframe}"
        )
        lines.append(f"Decision candle time: {record.decision_time}")
        lines.append(
            f"Rows used: {record.rows_used} | "
            f"Exclude latest candle: {'Yes' if record.exclude_latest else 'No'}"
        )
        lines.append("")

        lines.append(f"Action: {record.action}")
        lines.append(f"Heuristic score: {record.score:.2f}")
        lines.append(f"Heuristic confidence: {record.confidence:.1f}/100")
        lines.append(
            "Confidence is a weighted rule score, NOT a win probability."
        )
        lines.append("")

        intraday_meta = record.inputs.get("intraday_metadata") if isinstance(record.inputs, dict) else None

        if intraday_meta:
            lines.append("Intraday Multi-Timeframe Plan:")
            lines.append(f"  Market Regime: {intraday_meta.get('market_regime', 'N/A')}")
            lines.append(f"  Direction: {intraday_meta.get('direction', 'N/A')} | Status: {intraday_meta.get('status', 'N/A')}")
            lines.append(f"  Entry Reference: {intraday_meta.get('entry_reference', 'N/A')}")
            lines.append(f"  Stop Loss: {intraday_meta.get('stop_loss', 'N/A')}")
            lines.append(f"  Take Profit 1: {intraday_meta.get('take_profit_1', 'N/A')} (R:R {intraday_meta.get('reward_risk_1', 'N/A')})")
            lines.append(f"  Take Profit 2: {intraday_meta.get('take_profit_2', 'N/A')} (R:R {intraday_meta.get('reward_risk_2', 'N/A')})")
            lines.append(f"  Risk Distance: {intraday_meta.get('risk_distance', 'N/A')}")
            lines.append("")

        regime_meta = record.inputs.get("regime_and_microstructure") if isinstance(record.inputs, dict) else None
        if regime_meta:
            lines.append("Market Regime & Microstructure:")
            lines.append(f"  Trading Session: {regime_meta.get('session', 'N/A')}")
            s_ratio = regime_meta.get("spread_to_risk_ratio")
            s_str = f"{s_ratio:.2%}" if isinstance(s_ratio, (int, float)) else str(s_ratio)
            lines.append(f"  Spread-to-Risk Ratio: {s_str}")
            lines.append(f"  M15 Kaufman Efficiency: {regime_meta.get('m15_efficiency_ratio', 'N/A')}")
            lines.append(f"  M15 ATR Percentile: {regime_meta.get('m15_atr_percentile', 'N/A')}%")
            lines.append("")

        outcome_data = None
        if isinstance(record.inputs, dict):
            outcome_data = record.inputs.get("outcome")
        if not outcome_data and hasattr(record, "outcome"):
            outcome_data = getattr(record, "outcome")

        if outcome_data:
            lines.append("Signal Outcome & Forward Tracking:")
            if isinstance(outcome_data, dict):
                lines.append(f"  Status: {outcome_data.get('outcome', 'OPEN')}")
                r_val = outcome_data.get('outcome_r')
                if r_val is not None:
                    lines.append(f"  Realized R: {float(r_val):+.2f}R")
                lines.append(f"  Resolved At: {outcome_data.get('resolved_at', 'N/A')}")
                h_bars = outcome_data.get('holding_bars')
                if h_bars is not None:
                    lines.append(f"  Holding Bars: {h_bars} ({int(h_bars) * 5} mins)")
                if outcome_data.get("notes"):
                    lines.append(f"  Notes: {outcome_data['notes']}")
            else:
                lines.append(f"  Status: {getattr(outcome_data, 'outcome', 'OPEN')}")
                lines.append(f"  Realized R: {getattr(outcome_data, 'outcome_r', 0.0):+.2f}R")
                lines.append(f"  Resolved At: {getattr(outcome_data, 'resolved_at', 'N/A')}")
            lines.append("")

        lines.append("Rule contributions / Setup reasons:")
        if record.reasons:
            for reason in record.reasons:
                lines.append(f"  {reason}")
        else:
            lines.append("  No valid rule contributions.")

        if intraday_meta and intraday_meta.get("conflicts"):
            lines.append("")
            lines.append("Setup conflicts / Filter rejections:")
            for conflict in intraday_meta["conflicts"]:
                lines.append(f"  {conflict}")

        if record.warnings:
            lines.append("")
            lines.append("Warnings:")
            for warning in record.warnings:
                lines.append(f"  {warning}")

        if record.weights:
            lines.append("")
            lines.append("Rule weights:")
            for name, weight in record.weights.items():
                lines.append(f"  {name:<24} {float(weight):8.3f}")

        if record.inputs:
            lines.append("")
            lines.append("Decision inputs:")
            for name, value in record.inputs.items():
                if name in ("intraday_metadata", "regime_and_microstructure"):
                    continue
                lines.append(f"  {name}: {value}")

        lines.append("")
        lines.append(
            "Heuristic decision record only. No order was sent by this module."
        )

        return "\n".join(lines)

    @staticmethod
    def to_json(record: SignalRecord) -> str:
        payload = {
            "record_id": record.record_id,
            "created_at": record.created_at,
            "engine": record.engine,
            "engine_version": record.engine_version,
            "symbol": record.symbol,
            "timeframe": record.timeframe,
            "decision_time": record.decision_time,
            "action": record.action,
            "score": record.score,
            "confidence": record.confidence,
            "confidence_is_probability": False,
            "rows_used": record.rows_used,
            "exclude_latest": record.exclude_latest,
            "inputs": record.inputs,
            "reasons": record.reasons,
            "warnings": record.warnings,
            "weights": record.weights,
            "order_sent": False,
        }

        intraday_meta = record.inputs.get("intraday_metadata") if isinstance(record.inputs, dict) else None
        if intraday_meta:
            payload["intraday_mtf_plan"] = intraday_meta

        if isinstance(record.inputs, dict) and "outcome" in record.inputs:
            payload["outcome"] = record.inputs["outcome"]

        return json.dumps(payload, indent=2, ensure_ascii=True)
