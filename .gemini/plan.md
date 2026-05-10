# Project Plan: Candle Chart Backtest System

## 1. Overview
This project implements a stock backtesting and simulation system for Korean and US markets. It includes data fetching, multiple backtesting strategies, strategy comparison, and a daily simulation dashboard.

## 2. Directory Structure
```
candle-new/
├── .gemini/
│   ├── GEMINI.md       # Project instructions
│   └── plan.md         # This plan
├── data/               # Fetched stock data (CSV)
├── backtest/           # Backtest strategy implementations
│   ├── type1/
│   ├── type2/
│   └── type3/
├── simulation/         # Daily simulation and dashboard
│   ├── dashboard/      # HTML/CSS/JS files
│   └── engine.py       # Simulation logic
├── fetch_data.py       # Data acquisition script
├── backtest_compare.py # Strategy comparison script
└── main.py             # Main entry point
```

## 3. Implementation Phases

### Phase 1: Data Acquisition (`fetch_data.py`)
- [ ] Update `fetch_data.py` to include:
    - Group 1: KOSPI 200 (Dynamic)
    - Group 2: S&P 500 (Dynamic)
    - Group 3: Specified KR ETFs (Static list)
    - Group 4: Specified US ETFs (Static list)
- [ ] Fetch additional metrics:
    - PER, PBR (where available)
    - MA10D, MA50D
    - Dividend Payment Date, Dividend Amount, Yield, Payout Ratio
- [ ] Calculate `MA10M_UPDOWN` and inflection points.
- [ ] Implement incremental updates (only fetch new data).

### Phase 2: Backtest Strategies
- [ ] Implement Type 1: Inflection point based.
    - `type1_1`: Fixed 10 shares.
    - `type1_2`: All-in/All-out with initial capital.
- [ ] Implement Type 2: Trend maintenance based (`plus_days`/`minus_days`).
    - `type2_1`: 10 shares.
    - `type2_2`: All-in/All-out.
- [ ] Implement Type 3: DCA (Dollar Cost Averaging) every 3 months.
- [ ] Ensure all types output consistent CSV formats for comparison.

### Phase 3: Strategy Comparison (`backtest_compare.py`)
- [ ] Read result CSVs from all backtest types.
- [ ] Calculate total return, per-stock return, max drawdown, etc.
- [ ] Identify "Best Strategy" and related metrics (e.g., volume at evaluation).
- [ ] Output comparison table to console and CSV.

### Phase 4: Simulation & Dashboard
- [ ] Implement daily simulation engine:
    - Rule-based (from backtest strategies).
    - AI-based (OpenAI/Gemini API integration).
    - Manual input.
- [ ] Develop Dashboard (HTML/CSS/JS):
    - Daily decision log.
    - Portfolio status (shares, price, return).
    - Grouped view (Rule/AI/Manual).
    - Manual entry form.
- [ ] AI Prompt design for investment decisions.

## 4. Execution Strategy
- Use `uv` for package management and script execution.
- Use `uv add` for missing dependencies (e.g., `pandas`, `FinanceDataReader`, `yfinance`, `beautifulsoup4`, `openai`).
- Standardize data formats in `data/` to ensure interoperability between scripts.

## 5. Verification
- Validate data fetching for all groups.
- Run backtests and verify CSV outputs.
- Verify comparison logic with sample data.
- Test dashboard updates after simulation runs.
