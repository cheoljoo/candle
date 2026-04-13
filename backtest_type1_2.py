"""
backtest_type1_2.py

Type1-2 규칙:
  - MA10M 기준 -→+ 전환 시 가용 현금으로 살 수 있는 최대 주수 매수 (1주 단위)
  - +→- 전환 시 보유 주식 전량 매도, 매도 대금은 현금으로 보유
  - 초기 자본은 첫 매수 시 SHARES_PER_TRADE * 첫매수가로 자동 설정
  - 손실 매도 시 다음 매수 주수가 줄어들고, 이익 매도 시 늘어남
  - 기간 종료 시 미매도 보유분은 --to 기준 평가가격으로 손익 계산

type1 과의 차이:
  - type1: 매번 고정 SHARES_PER_TRADE (10주) 매수 (현금 무관)
  - type1-2: 가용 현금 안에서 최대 주수 매수 (손익에 따라 주수 변동)

CLI:
  --from       백테스트 시작일 (기본값: 2년 전 01-01)
  --to         백테스트 종료일/평가 기준일 (기본값: 오늘)
  --output_csv 결과 CSV 저장 경로 (기본값: backtest_type1_2.csv)
"""

from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from analyze import print_table
from backtest_type1 import (
    SHARES_PER_TRADE,
    BacktestWindow,
    append_group_summary,
    build_universe,
    build_window,
    default_from_date,
    get_rank_at_date,
    load_price_frame,
    load_rank_table,
    save_window_result,
)


def default_output_csv() -> str:
    return "backtest_type1_2.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Type1-2 백테스트: 첫 매수 시 SHARES_PER_TRADE주만큼의 현금으로 시작하고, "
            "이후 가용 현금으로 살 수 있는 최대 주수를 매수합니다. "
            "MA10M -→+ 전환 시 매수, +→- 전환 시 전량 매도."
        ),
        epilog=(
            "예시:\n"
            "  uv run python backtest_type1_2.py\n"
            "  uv run python backtest_type1_2.py --from 2020-01-01 --to 2025-12-31"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--from", dest="from_date", default=default_from_date(), help="백테스트 시작일 (YYYY-MM-DD)")
    parser.add_argument("--to", dest="to_date", default=date.today().isoformat(), help="백테스트 종료일이자 평가 기준일 (YYYY-MM-DD)")
    parser.add_argument("--output_csv", dest="output_csv", default=default_output_csv(), help="결과 CSV 저장 경로")
    return parser.parse_args()


def simulate_type1_2(df: pd.DataFrame, window: BacktestWindow) -> dict:
    """
    현금 추적 type1 시뮬레이션.
    - 초기 자본: 첫 매수 신호 발생 시 SHARES_PER_TRADE * 매수가로 설정
    - 이후 매수: 가용 현금으로 최대 주수(1주 단위) 매수
    - 매도: 보유 전량 매도, 현금 회수
    """
    start_ts = pd.Timestamp(window.start)
    end_ts = pd.Timestamp(window.end)
    period_df = df.loc[(df.index >= start_ts) & (df.index <= end_ts)].copy()
    previous_row = df.loc[df.index < start_ts].tail(1)

    empty = {
        "period": window.title,
        "current_price": 0.0,
        "current_date": end_ts.strftime("%Y-%m-%d"),
        "price_date": "-",
        "buy_count": 0,
        "sell_count": 0,
        "shares_held": 0,
        "cash": 0.0,
        "initial_capital": 0.0,
        "total_buy_amount": 0.0,
        "closed_buy_amount": 0.0,
        "realized_profit": 0.0,
        "closed_return_pct": 0.0,
        "unrealized_profit": 0.0,
        "total_profit": 0.0,
        "return_pct": 0.0,
        "holding_status": "기간 데이터 없음",
        "last_buy_date": "-",
        "last_sell_date": "-",
    }

    if period_df.empty:
        return empty

    signal_df = pd.concat([previous_row, period_df]) if not previous_row.empty else period_df
    signal_df = signal_df.dropna(subset=["MA10M"])
    if len(signal_df) < 2:
        return {**empty, "current_price": round(float(period_df["Close"].iloc[-1]), 2), "holding_status": "신호 없음"}

    valuation_price = float(period_df["Close"].iloc[-1])
    valuation_price_date = period_df.index[-1]
    is_positive = signal_df["Close"] > signal_df["MA10M"]

    cash = 0.0
    initial_capital = 0.0
    shares_held = 0
    buy_count = 0
    sell_count = 0
    total_buy_amount = 0.0
    closed_buy_amount = 0.0
    realized_profit = 0.0
    entry_cost = 0.0
    last_buy_date = "-"
    last_sell_date = "-"

    for i in range(1, len(signal_df)):
        trade_date = signal_df.index[i]
        if trade_date < start_ts or trade_date > end_ts:
            continue

        prev_positive = bool(is_positive.iloc[i - 1])
        curr_positive = bool(is_positive.iloc[i])
        trade_price = float(signal_df["Close"].iloc[i])

        if not prev_positive and curr_positive and shares_held == 0:
            if initial_capital == 0.0:
                # 첫 매수: 초기 자본 설정 후 SHARES_PER_TRADE주 매수
                initial_capital = SHARES_PER_TRADE * trade_price
                cash = initial_capital
            shares = int(cash // trade_price)
            if shares > 0:
                spent = shares * trade_price
                shares_held = shares
                entry_cost = spent
                cash -= spent
                total_buy_amount += spent
                buy_count += 1
                last_buy_date = trade_date.strftime("%Y-%m-%d")

        elif prev_positive and not curr_positive and shares_held > 0:
            proceeds = trade_price * shares_held
            closed_buy_amount += entry_cost
            realized_profit += proceeds - entry_cost
            cash += proceeds
            shares_held = 0
            entry_cost = 0.0
            sell_count += 1
            last_sell_date = trade_date.strftime("%Y-%m-%d")

    unrealized_profit = valuation_price * shares_held - entry_cost if shares_held else 0.0
    total_profit = realized_profit + unrealized_profit
    return_pct = (total_profit / initial_capital * 100) if initial_capital else 0.0
    closed_return_pct = (realized_profit / closed_buy_amount * 100) if closed_buy_amount else 0.0

    holding_status = "보유중(기간 종료가 평가)" if shares_held else "미보유"
    if buy_count == 0:
        holding_status = "매수 없음"

    return {
        "period": window.title,
        "current_price": round(valuation_price, 2),
        "current_date": end_ts.strftime("%Y-%m-%d"),
        "price_date": valuation_price_date.strftime("%Y-%m-%d"),
        "buy_count": buy_count,
        "sell_count": sell_count,
        "shares_held": shares_held,
        "cash": round(cash, 2),
        "initial_capital": round(initial_capital, 2),
        "total_buy_amount": round(total_buy_amount, 2),
        "closed_buy_amount": round(closed_buy_amount, 2),
        "realized_profit": round(realized_profit, 2),
        "closed_return_pct": round(closed_return_pct, 2),
        "unrealized_profit": round(unrealized_profit, 2),
        "total_profit": round(total_profit, 2),
        "return_pct": round(return_pct, 2),
        "holding_status": holding_status,
        "last_buy_date": last_buy_date,
        "last_sell_date": last_sell_date,
    }


def run_group_backtest(group_name: str, items: list[dict], window: BacktestWindow) -> pd.DataFrame:
    rows: list[dict] = []
    rank_table = load_rank_table(group_name)

    for item in items:
        df = load_price_frame(item["stocks_dir"] / f"{item['ticker']}.csv")
        if df is None:
            continue

        result = simulate_type1_2(df, window)
        rank_str = (
            get_rank_at_date(rank_table, item["ticker"], result["last_buy_date"])
            if result["shares_held"] > 0 and result["last_buy_date"] != "-"
            else "-"
        )
        rows.append(
            {
                "그룹": group_name,
                "기간": result["period"],
                "티커": item["ticker"],
                "종목명": item["name"],
                "시가총액": item["marcap"],
                "평가종가": result["current_price"],
                "평가기준일": result["current_date"],
                "평가가격일": result["price_date"],
                "상태": result["holding_status"],
                "보유주식수": result["shares_held"],
                "현금잔고": result["cash"],
                "초기자본": result["initial_capital"],
                "매수횟수": result["buy_count"],
                "매도횟수": result["sell_count"],
                "총매수금액": result["total_buy_amount"],
                "_사고판매수금액": result["closed_buy_amount"],
                "사고판수익": result["realized_profit"],
                "사고판수익률(%)": result["closed_return_pct"],
                "실현손익": result["realized_profit"],
                "미실현손익": result["unrealized_profit"],
                "총손익": result["total_profit"],
                "수익률(%)": result["return_pct"],
                "마지막매수일": result["last_buy_date"],
                "매수일_시총순위": rank_str,
                "마지막매도일": result["last_sell_date"],
            }
        )

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.sort_values(by=["수익률(%)", "총손익", "티커"], ascending=[False, False, True]).reset_index(drop=True)
    return append_group_summary(df, group_name)


def print_group_result(group_name: str, window: BacktestWindow, df: pd.DataFrame) -> None:
    bar = "=" * 150
    print(f"\n{bar}")
    print(f"[{window.title}] {group_name} Type1-2 백테스트 (현금 추적)")
    print(bar)

    if df.empty:
        print("  결과 없음")
        return

    def format_number(value):
        if value == "" or pd.isna(value):
            return ""
        number = float(value)
        return int(number) if number.is_integer() else round(number, 2)

    display_df = df.drop(columns=["_사고판매수금액"]).copy()
    for column in ["평가종가", "현금잔고", "초기자본", "총매수금액", "사고판수익", "사고판수익률(%)", "실현손익", "미실현손익", "총손익", "수익률(%)"]:
        display_df[column] = display_df[column].map(format_number)

    right_cols = {
        "평가종가", "보유주식수", "현금잔고", "초기자본", "매수횟수", "매도횟수",
        "총매수금액", "사고판수익", "사고판수익률(%)", "실현손익", "미실현손익",
        "총손익", "수익률(%)", "매수일_시총순위",
    }
    print_table(display_df, right_cols=right_cols)


def main() -> None:
    args = parse_args()
    window = build_window(args.from_date, args.to_date)

    print("Type1-2 백테스트를 시작합니다...")
    print(f"기준일: {datetime.now().strftime('%Y-%m-%d')}")
    print(f"기간: {window.title}")
    print(f"규칙: 첫 매수 = {SHARES_PER_TRADE}주로 초기자본 설정, 이후 가용 현금으로 최대 주수 매수 / +→- 전량 매도")

    group_results: list[pd.DataFrame] = []
    for group_name, items in build_universe():
        df = run_group_backtest(group_name, items, window)
        if not df.empty:
            print_group_result(group_name, window, df)
            group_results.append(df)

    saved = save_window_result(args.output_csv, group_results)
    if saved:
        print(f"\n결과 저장: {saved}")


if __name__ == "__main__":
    main()
