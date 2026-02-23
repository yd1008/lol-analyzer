# HEARTBEAT.md - Stock Trader Autonomous Project

## Primary Mission
Build, test, and validate a profitable stock trading system with $1000 initial capital.

## End State
- Trading logic validated with real/paper trades
- Demonstrable profit from $1000 starting fund
- Only then: report back to user

## Progress Log

### 2026-02-22 20:35 EST - VM Verified Healthy / Trading Unblocked
- Containers running; API reachable; `/v1/health` => ok (db ok, redis ok)
- `risk_state`: max_drawdown_today=0.00016, trading_paused_until=NULL
- `trading_supervisor_state`: NORMAL

### 2026-02-22 20:40 EST - Backtest Running
- Started 2024 full-year backtest with $10,000 initial capital
- Run ID: `cb8d3450-7b76-4777-958a-0c05981dfe70`
- Progress: 3/252 steps (1.2%)
- Symbols: SPY, QQQ, AAPL, MSFT
- Using legacy fallback engine (LEAN launcher not installed on VM)

### 2026-02-22 21:46 EST - Simulation Runner Not Processing Queue (Needs Fix)
- `stock-trader-sim-runner-1` was restarting continuously (exit=0) and the simulation queue was not draining.

### 2026-02-23 01:52 EST - Runner Mode Enabled / Queue Draining
- `SIMULATION_EXECUTOR_MODE=runner` is now set in the sim-runner container.
- `stock-trader-sim-runner-1` is staying up (no restart loop).
- Simulation queue is no longer accumulating (no `queued` runs).
- One simulation run is currently `running`: `d6e7f890-1234-4abc-9def-123456789abc`.

### 2026-02-23 02:43 EST - Simulation Queue Cleared
- `stock-trader-sim-runner-1` is up.
- `simulation_runs`: no `queued` or `running` runs (only completed/failed).
- API health: `/v1/health` => ok (db ok, redis ok)

### 2026-02-23 07:01 EST - Latest Simulation Completed (Unprofitable) / LEAN Launcher Still Missing
- Simulation run: `d6e7f890-1234-4abc-9def-123456789abc` => `completed`
- Result: total_return=-23.84%, max_drawdown=27.71%, win_rate=31.56%
- `legacy_fallback`: true
- Runtime error: `LEAN launcher command is unavailable`
- Note: LEAN run logs for `cb8d3450-7b76-4777-958a-0c05981dfe70` show only `LEAN launcher command is unavailable`

### Next Tasks (Priority Order)
1. [x] Verify trading is unblocked on VM
2. [x] Pull latest code to VM and restart containers
3. [ ] Improve trading strategy:
   - Research momentum + mean reversion hybrid
   - Better signal generation
   - Position sizing based on volatility
4. [ ] Run backtests to validate profitability
5. [ ] Set up Alpaca paper trading (need API keys)
6. [ ] Validate with paper trading before live

## Current Issues
- LEAN launcher missing on VM (LEAN runtime unavailable; runs fall back and/or fail)
- Micro risk policy currently inactive in `simulate` mode (guardrails not enforcing)
- No Alpaca API keys configured (paper trading)
- No OpenCode API configured (LLM using mock)
- Need to validate strategy profitability

## Server Access
- SSH: `ssh -i ~/.ssh/stock-trader-vm trader@159.203.165.9`
- API: http://159.203.165.9:8080

## Key Files
- Algorithm: `lean_projects/stock_trader/Main.py`
- Pipeline: `app/services/pipeline.py`
- Signal Engine: `app/services/signal_engine.py`
- Decision Engine: `app/services/decision_engine.py`

## Knowledge Base
- Trading research + pro-level process notes: `memory/stock-trader-playbook.md`

---
*This is an autonomous mission - working continuously until profitable*
