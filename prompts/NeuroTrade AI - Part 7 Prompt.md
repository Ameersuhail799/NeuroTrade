You are building "NeuroTrade AI" - Part 7: Feedback Loop (Auto-Training).
This is a PERSONAL USE desktop trading application.

CONTEXT: Parts 1-6 are complete. Now build the feedback loop that makes the AI learn.

TASK: Create the Feedback Loop system that enables auto-training from trade results.

REQUIREMENTS:

1. Create core/feedback_loop.py:
   - Class FeedbackLoop
   - This is the LEARNING engine of NeuroTrade AI

2. Core Concept:
   When a testing trade closes:
   - If WIN (TP hit): Reward the brain (+)
   - If LOSS (SL hit): Penalize the brain (-)
   - Brain adjusts its weights/parameters
   - Next decision is slightly better

3. Methods:
   
   - Method: process_trade_result(trade_result)
     Input: TradeResult object (from Part 6)
     Process:
       a) Determine if WIN or LOSS
       b) Extract the original signal that led to this trade
       c) Analyze what worked / what didn't
       d) Update brain parameters
       e) Save learning to database
     Output: LearningReport object
   
   - Method: calculate_reward(trade_result)
     WIN: reward = +1.0 (base) + profit_bonus
     LOSS: reward = -1.0 (base) - loss_penalty
     Returns: float reward value
   
   - Method: update_brain(signal, reward)
     Adjust AI Brain confidence thresholds
     Adjust pattern weights
     Adjust indicator importance
     Returns: Updated brain parameters
   
   - Method: get_learning_history()
     Returns: List of all learning events
   
   - Method: get_brain_evolution()
     Returns: Brain state changes over time

4. Learning Parameters:
   Store these adjustable weights:
   {
     "trend_weight": 1.0,
     "rsi_weight": 1.0,
     "macd_weight": 1.0,
     "pattern_weight": 1.0,
     "ma_weight": 1.0,
     "sr_weight": 1.0,
     "confidence_threshold": 70,
     "sl_multiplier": 1.5,
     "rr_ratio": 2.0
   }
   
   - WIN: Increase weight of factors that contributed
   - LOSS: Decrease weight of factors that contributed

5. Learning Database:
   Table: learning_history
   - id, trade_id, signal_type, result (WIN/LOSS), reward,
     brain_params_before (JSON), brain_params_after (JSON), timestamp
   
   Table: brain_params
   - id, param_name, param_value, updated_at

6. Brain State Management:
   - Method: update_brain_state()
     Calculate based on:
     * Total trades: < 50 = LEARNING
     * Total trades: 50-200 = TRAINED
     * Total trades: > 200 = EXPERT
     * Accuracy: > 60% upgrades state
     * Accuracy: < 40% downgrades state
   
   - Method: get_brain_status()
     Returns:
     {
       "state": "TRAINED",
       "total_trades": 156,
       "wins": 112,
       "losses": 44,
       "accuracy": 71.8,
       "current_streak": 4,
       "best_streak": 12,
       "experience_points": 1560
     }

7. Auto-Training Loop:
   - Method: start_auto_training()
     Begins continuous learning cycle:
     1. Collect market data
     2. Generate signal
     3. Execute testing trade
     4. Wait for trade to close
     5. Process result
     6. Update brain
     7. Repeat
   
   - Method: stop_auto_training()
     Stops the learning cycle
   
   - Property: is_training (bool)

8. Statistics Tracking:
   - Method: get_daily_stats()
   - Method: get_weekly_stats()
   - Method: get_monthly_stats()
   - Method: get_accuracy_trend()
     Returns accuracy over time for chart display

9. Integration:
   - Receives TradeResult from TradeExecutor (Part 6)
   - Updates AIBrain (Part 5) parameters
   - Stores data in SQLite (Part 4)
   - Reports to Dashboard (Part 8)

IMPORTANT RULES:
- All code in English
- Learning must be GRADUAL (not jumping)
- Store ALL learning events
- Brain must improve over time
- Never forget past lessons

Write complete, working code. This is what makes the AI "learn" and improve.