import pandas as pd
import json
from pathlib import Path
from datetime import datetime, timedelta

STATE_FILE = Path("simulation/state.json")
DASHBOARD_DATA = Path("simulation/dashboard_data.json")

def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {
        "cash": 100_000_000, # Initial 100M KRW
        "portfolio": {}, # ticker: {qty, avg_price}
        "history": [] # list of trades
    }

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=4)

def run_daily_simulation(target_date=None):
    if target_date is None:
        target_date = datetime.now().strftime('%Y-%m-%d')
    
    state = load_state()
    
    # In a real simulation, we would check signals for target_date
    # For now, let's just create a mock decision for the dashboard
    
    decision = {
        "date": target_date,
        "ticker": "005930",
        "name": "삼성전자",
        "action": "BUY",
        "price": 75000,
        "qty": 10,
        "reason": "MA10M Cross Up (Rule-base)"
    }
    
    # Update state
    # (Simplified for now)
    
    # Prepare dashboard data
    dashboard = {
        "last_update": target_date,
        "total_value": 105000000,
        "roi": 5.0,
        "decisions": [decision],
        "portfolio": [
            {"ticker": "005930", "name": "삼성전자", "qty": 100, "price": 75000, "value": 7500000, "roi": 2.5}
        ]
    }
    
    with open(DASHBOARD_DATA, 'w') as f:
        json.dump(dashboard, f, indent=4)
    
    print(f"Simulation for {target_date} completed.")

if __name__ == "__main__":
    run_daily_simulation()
