"""
backtest_type4.py

Type4 규칙:
  - KOSPI: 시가총액 상위 30, S&P500: 시가총액 상위 100만 매수 후보
  - 시가총액 순위는 현재 시가총액과 현재가로 유통주식수를 근사한 뒤,
    과거 종가에 곱해 시점별 시가총액을 추정하는 방식으로 계산
  - 매수는 `- -> +` 전환이 발생했고 rank 조건도 만족할 때만 실행
  - 매도는 `+ -> -` 전환이 발생하면 즉시 실행
  - 기간 시작 시 이미 `+` 인 종목은 type1과 동일하게 매수하지 않음
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import FinanceDataReader as fdr
import pandas as pd

from analyze import print_table
from backtest_type1 import (
    SHARES_PER_TRADE,
    BacktestWindow,
    append_group_summary,
    build_universe,
    build_window,
    default_to_date,
    get_rank_at_date,
    load_price_frame,
    load_rank_table,
    save_window_result,
)
from fetch_data import fetch_us_marketcap_table, normalize_symbol

DEFAULT_FROM_DATE = "2020-01-01"
KOSPI_TOP_N = 30
SP500_TOP_N = 100


@dataclass(frozen=True)
class RankContext:
    current_top_tickers: set[str]
    historical_top_lookup: dict[pd.Timestamp, set[str]]


def default_output_csv() -> str:
    return "backtest_type4.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Type4 백테스트: KOSPI 상위 30 / S&P500 상위 100 시가총액 조건을 만족하는 종목만 "
            "MA10M 기준 -→+ 전환에서 매수하고, +→- 전환에서 매도합니다."
        ),
        epilog=(
            "예시:\n"
            "  uv run python backtest_type4.py\n"
            "  uv run python backtest_type4.py --from 2020-01-01 --to 2026-04-12\n"
            "  uv run python backtest_type4.py --output_csv data/backtest_type4.csv"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--from",
        dest="from_date",
        default=DEFAULT_FROM_DATE,
        help="백테스트 시작일 (YYYY-MM-DD, 기본값: 2020-01-01)",
    )
    parser.add_argument(
        "--to",
        dest="to_date",
        default=default_to_date(),
        help="백테스트 종료일이자 평가 기준일 (YYYY-MM-DD, 기본값: 오늘)",
    )
    parser.add_argument(
        "--output_csv",
        dest="output_csv",
        default=default_output_csv(),
        help="결과 CSV 저장 경로 (기본값: backtest_type4.csv)",
    )
    return parser.parse_args()


def build_rank_contexts() -> dict[str, RankContext]:
    universe = build_universe()
    contexts: dict[str, RankContext] = {}

    kospi_listing = fdr.StockListing("KOSPI")
    kospi_listing["Code"] = kospi_listing["Code"].astype(str).str.zfill(6)
    kospi_shares = dict(zip(kospi_listing["Code"], pd.to_numeric(kospi_listing["Stocks"], errors="coerce")))
    kospi_current_top = set(
        kospi_listing.sort_values("Marcap", ascending=False).head(KOSPI_TOP_N)["Code"].astype(str).tolist()
    )

    us_marketcap = fetch_us_marketcap_table()

    for group_name, items in universe:
        if group_name == "ETF":
            continue

        close_frame: dict[str, pd.Series] = {}
        shares_outstanding: dict[str, float] = {}

        if group_name == "KOSPI 200":
            current_top = kospi_current_top
        else:
            sp500_symbols = {str(item["ticker"]) for item in items}
            sp500_marketcap = us_marketcap[us_marketcap["normalized_symbol"].isin({normalize_symbol(sym) for sym in sp500_symbols})]
            current_top = set()
            for _, row in sp500_marketcap.sort_values("marketcap", ascending=False).head(SP500_TOP_N).iterrows():
                normalized = row["normalized_symbol"]
                match = next((sym for sym in sp500_symbols if normalize_symbol(sym) == normalized), None)
                if match:
                    current_top.add(match)

        for item in items:
            ticker = str(item["ticker"])
            df = load_price_frame(item["stocks_dir"] / f"{ticker}.csv")
            if df is None or df.empty:
                continue
            close_frame[ticker] = pd.to_numeric(df["Close"], errors="coerce")

            if group_name == "KOSPI 200":
                shares = kospi_shares.get(ticker)
            else:
                row = us_marketcap[us_marketcap["normalized_symbol"] == normalize_symbol(ticker)].head(1)
                shares = None
                if not row.empty:
                    latest_close = float(close_frame[ticker].dropna().iloc[-1]) if not close_frame[ticker].dropna().empty else 0.0
                    marketcap = float(row["marketcap"].iloc[0])
                    shares = (marketcap / latest_close) if latest_close > 0 else None
            if shares and pd.notna(shares) and float(shares) > 0:
                shares_outstanding[ticker] = float(shares)

        approx_cap = {}
        for ticker, close_series in close_frame.items():
            shares = shares_outstanding.get(ticker)
            if not shares:
                continue
            approx_cap[ticker] = close_series * shares
        if not approx_cap:
            continue

        cap_df = pd.DataFrame(approx_cap).sort_index()
        top_n = KOSPI_TOP_N if group_name == "KOSPI 200" else SP500_TOP_N
        historical_top_lookup: dict[pd.Timestamp, set[str]] = {}
        for trade_date, row in cap_df.iterrows():
            valid = row.dropna().sort_values(ascending=False).head(top_n)
            historical_top_lookup[pd.Timestamp(trade_date)] = set(valid.index.tolist())

        contexts[group_name] = RankContext(
            current_top_tickers=current_top,
            historical_top_lookup=historical_top_lookup,
        )

    return contexts


def can_buy_type4(group_name: str, ticker: str, trade_date: pd.Timestamp, rank_context: RankContext) -> bool:
    if ticker in rank_context.current_top_tickers:
        return True
    return ticker in rank_context.historical_top_lookup.get(pd.Timestamp(trade_date), set())


def empty_result(window: BacktestWindow, current_price: float, price_date: str, status: str) -> dict:
    return {
        "period": window.title,
        "current_price": round(current_price, 2),
        "current_date": window.end,
        "price_date": price_date,
        "buy_count": 0,
        "sell_count": 0,
        "shares_held": 0,
        "total_buy_amount": 0.0,
        "closed_buy_amount": 0.0,
        "realized_profit": 0.0,
        "closed_return_pct": 0.0,
        "unrealized_profit": 0.0,
        "total_profit": 0.0,
        "return_pct": 0.0,
        "holding_status": status,
        "last_buy_date": "-",
        "last_sell_date": "-",
    }


def simulate_type4(df: pd.DataFrame, window: BacktestWindow, group_name: str, ticker: str, rank_context: RankContext) -> dict:
    start_ts = pd.Timestamp(window.start)
    end_ts = pd.Timestamp(window.end)
    period_df = df.loc[(df.index >= start_ts) & (df.index <= end_ts)].copy()
    previous_row = df.loc[df.index < start_ts].tail(1)
    if period_df.empty:
        return empty_result(window, 0.0, "-", "기간 데이터 없음")

    signal_df = pd.concat([previous_row, period_df]) if not previous_row.empty else period_df
    signal_df = signal_df.dropna(subset=["MA10M"])
    period_df = period_df.dropna(subset=["MA10M"])
    if period_df.empty or len(signal_df) < 2:
        return empty_result(window, float(df["Close"].iloc[-1]), "-", "신호 없음")

    valuation_price = float(period_df["Close"].iloc[-1])
    valuation_price_date = period_df.index[-1]
    is_positive = signal_df["Close"] > signal_df["MA10M"]

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

        if (
            shares_held == 0
            and not prev_positive
            and curr_positive
            and can_buy_type4(group_name, ticker, trade_date, rank_context)
        ):
            shares_held = SHARES_PER_TRADE
            entry_cost = trade_price * SHARES_PER_TRADE
            total_buy_amount += entry_cost
            buy_count += 1
            last_buy_date = trade_date.strftime("%Y-%m-%d")
            continue

        if shares_held > 0 and prev_positive and not curr_positive:
            proceeds = trade_price * shares_held
            closed_buy_amount += entry_cost
            realized_profit += proceeds - entry_cost
            shares_held = 0
            entry_cost = 0.0
            sell_count += 1
            last_sell_date = trade_date.strftime("%Y-%m-%d")

    unrealized_profit = valuation_price * shares_held - entry_cost if shares_held else 0.0
    total_profit = realized_profit + unrealized_profit
    return_pct = (total_profit / total_buy_amount * 100) if total_buy_amount else 0.0
    closed_return_pct = (realized_profit / closed_buy_amount * 100) if closed_buy_amount else 0.0
    holding_status = "보유중(기간 종료가 평가)" if shares_held else "미보유"
    if buy_count == 0:
        holding_status = "매수 없음"

    return {
        "period": window.title,
        "current_price": round(valuation_price, 2),
        "current_date": window.end,
        "price_date": valuation_price_date.strftime("%Y-%m-%d"),
        "buy_count": buy_count,
        "sell_count": sell_count,
        "shares_held": shares_held,
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


def simulate_type4_capital(
    df: pd.DataFrame,
    window: BacktestWindow,
    initial_capital: float,
    group_name: str,
    ticker: str,
    rank_context: RankContext | None,
) -> dict:
    if rank_context is None:
        return {
            "shares_held": 0,
            "cash": round(initial_capital, 2),
            "total_asset": round(initial_capital, 2),
            "profit": 0.0,
            "return_pct": 0.0,
            "buy_count": 0,
            "sell_count": 0,
            "last_buy_date": "-",
            "last_sell_date": "-",
            "holding_status": "미지원",
        }

    start_ts = pd.Timestamp(window.start)
    end_ts = pd.Timestamp(window.end)
    period_df = df.loc[(df.index >= start_ts) & (df.index <= end_ts)].copy()
    previous_row = df.loc[df.index < start_ts].tail(1)
    signal_df = pd.concat([previous_row, period_df]) if not previous_row.empty else period_df
    signal_df = signal_df.dropna(subset=["MA10M"])
    period_df = period_df.dropna(subset=["MA10M"])
    if period_df.empty or len(signal_df) < 2:
        return {
            "shares_held": 0,
            "cash": round(initial_capital, 2),
            "total_asset": round(initial_capital, 2),
            "profit": 0.0,
            "return_pct": 0.0,
            "buy_count": 0,
            "sell_count": 0,
            "last_buy_date": "-",
            "last_sell_date": "-",
            "holding_status": "신호 없음",
        }

    cash = initial_capital
    shares_held = 0
    buy_count = 0
    sell_count = 0
    last_buy_date = "-"
    last_sell_date = "-"
    is_positive = signal_df["Close"] > signal_df["MA10M"]

    for i in range(1, len(signal_df)):
        trade_date = signal_df.index[i]
        if trade_date < start_ts or trade_date > end_ts:
            continue

        prev_positive = bool(is_positive.iloc[i - 1])
        curr_positive = bool(is_positive.iloc[i])
        trade_price = float(signal_df["Close"].iloc[i])

        if (
            shares_held == 0
            and not prev_positive
            and curr_positive
            and can_buy_type4(group_name, ticker, trade_date, rank_context)
        ):
            shares = int(cash // trade_price)
            if shares > 0:
                spent = shares * trade_price
                shares_held = shares
                cash -= spent
                buy_count += 1
                last_buy_date = trade_date.strftime("%Y-%m-%d")
            continue

        if shares_held > 0 and prev_positive and not curr_positive:
            cash += shares_held * trade_price
            shares_held = 0
            sell_count += 1
            last_sell_date = trade_date.strftime("%Y-%m-%d")

    valuation_price = float(period_df["Close"].iloc[-1])
    total_asset = cash + shares_held * valuation_price
    profit = total_asset - initial_capital
    holding_status = "보유중(기간 종료가 평가)" if shares_held else "미보유"
    if buy_count == 0:
        holding_status = "매수 없음"

    return {
        "shares_held": shares_held,
        "cash": round(cash, 2),
        "total_asset": round(total_asset, 2),
        "profit": round(profit, 2),
        "return_pct": round((profit / initial_capital) * 100, 2),
        "buy_count": buy_count,
        "sell_count": sell_count,
        "last_buy_date": last_buy_date,
        "last_sell_date": last_sell_date,
        "holding_status": holding_status,
    }


def run_group_backtest(group_name: str, items: list[dict], window: BacktestWindow, rank_contexts: dict[str, RankContext]) -> pd.DataFrame:
    rows: list[dict] = []
    rank_context = rank_contexts.get(group_name)
    if rank_context is None:
        return pd.DataFrame()

    rank_table = load_rank_table(group_name)

    for item in items:
        ticker = str(item["ticker"])
        df = load_price_frame(item["stocks_dir"] / f"{ticker}.csv")
        if df is None:
            continue
        result = simulate_type4(df, window, group_name, ticker, rank_context)
        rank_str = (
            get_rank_at_date(rank_table, ticker, result["last_buy_date"])
            if result["shares_held"] > 0 and result["last_buy_date"] != "-"
            else "-"
        )
        rows.append(
            {
                "그룹": group_name,
                "기간": result["period"],
                "티커": ticker,
                "종목명": item["name"],
                "시가총액": item["marcap"],
                "평가종가": result["current_price"],
                "평가기준일": result["current_date"],
                "평가가격일": result["price_date"],
                "상태": result["holding_status"],
                "보유주식수": result["shares_held"],
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
                "현재상위조건": "Y" if ticker in rank_context.current_top_tickers else "",
                "마지막매수일": result["last_buy_date"],
                "매수일_시총순위": rank_str,
                "마지막매도일": result["last_sell_date"],
            }
        )

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).sort_values(by=["수익률(%)", "총손익", "티커"], ascending=[False, False, True]).reset_index(drop=True)
    return append_group_summary(df, group_name)


def print_group_result(group_name: str, window: BacktestWindow, df: pd.DataFrame) -> None:
    bar = "=" * 150
    print(f"\n{bar}")
    print(f"[{window.title}] {group_name} Type4 백테스트")
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
    for column in ["평가종가", "총매수금액", "사고판수익", "사고판수익률(%)", "실현손익", "미실현손익", "총손익", "수익률(%)"]:
        display_df[column] = display_df[column].map(format_number)

    right_cols = {"평가종가", "보유주식수", "매수횟수", "매도횟수", "총매수금액", "사고판수익", "사고판수익률(%)", "실현손익", "미실현손익", "총손익", "수익률(%)", "매수일_시총순위"}
    print_table(display_df, right_cols=right_cols)


def main() -> None:
    args = parse_args()
    window = build_window(args.from_date, args.to_date)

    print("Type4 백테스트를 시작합니다...")
    print(f"기준일: {datetime.now().strftime('%Y-%m-%d')}")
    print(f"기간: {window.title}")
    print("규칙: KOSPI 상위 30 / S&P500 상위 100 시가총액 조건을 만족하는 + 신호만 매수, - 신호면 매도")

    rank_contexts = build_rank_contexts()
    group_results: list[pd.DataFrame] = []
    for group_name, items in build_universe():
        if group_name == "ETF":
            continue
        df = run_group_backtest(group_name, items, window, rank_contexts)
        group_results.append(df)
        print_group_result(group_name, window, df)

    output_path = save_window_result(args.output_csv, group_results)
    if output_path:
        print(f"\n→ CSV 저장: {output_path}")


if __name__ == "__main__":
    main()
