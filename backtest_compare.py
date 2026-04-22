"""
backtest_compare.py

동일 초기자금 기준으로 아래 4가지 전략을 비교한다.

- type1: MA10M -→+ 전환 시 전액 매수 / +→- 전환 시 전량 매도
- type2: MA10M 확인일수(기본 33/5) 충족 시 전액 매수 / 전량 매도
- type3: 신호와 무관하게 3개월마다 같은 금액을 적립식으로 매수 후 보유
- type4: 시가총액 상위 조건(KOSPI 30 / S&P500 100)을 만족하는 `+` 신호만 매수 / `-`면 매도

초기자금:
- KOSPI 200: 10,000,000 KRW
- S&P500 / ETF: 10,000 USD
- 단, type4는 slot 기준으로 별도 배분:
  - KOSPI: `10,000,000 / 30`
  - S&P500: `10,000 / 100`
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from analyze import print_table
from backtest_type1 import BacktestWindow, build_universe, build_window, get_rank_at_date, load_price_frame, load_rank_table
from backtest_type1_2 import simulate_type1_2
from backtest_type2 import compute_volume_metrics
from backtest_type4 import KOSPI_TOP_N, SP500_TOP_N, build_rank_contexts, simulate_type4_capital
from backtest_type4_2 import simulate_type4_2


DEFAULT_FROM_DATE = "2020-01-01"


@dataclass(frozen=True)
class CapitalResult:
    shares_held: int
    cash: float
    total_asset: float
    profit: float
    return_pct: float
    buy_count: int
    sell_count: int
    last_buy_date: str
    last_sell_date: str
    holding_status: str


def default_to_date() -> str:
    return date.today().isoformat()


def default_output_csv() -> str:
    return "backtest_compare.csv"


def type4_slot_count(group_name: str) -> int | None:
    if group_name == "KOSPI 200":
        return KOSPI_TOP_N
    if group_name == "S&P500":
        return SP500_TOP_N
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "동일 초기자금 기준으로 type1 / type2 / type3 / type4 자산 상태를 비교합니다. "
            "type1/type2는 매수 시 가용 현금 전액으로 가능한 최대 주수를 매수하고, "
            "type3는 3개월마다 동일 금액을 적립식으로 매수합니다."
        ),
        epilog=(
            "예시:\n"
            "  uv run python backtest_compare.py\n"
            "  uv run python backtest_compare.py --to 2026-04-12 --plus_days 33 --minus_days 5\n"
            "  uv run python backtest_compare.py --output_csv data/backtest_compare.csv"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--from",
        dest="from_date",
        default=DEFAULT_FROM_DATE,
        help="비교 시작일 (YYYY-MM-DD, 기본값: 2020-01-01)",
    )
    parser.add_argument(
        "--to",
        dest="to_date",
        default=default_to_date(),
        help="종료일이자 평가 기준일 (YYYY-MM-DD, 기본값: 오늘)",
    )
    parser.add_argument(
        "--plus_days",
        type=int,
        default=33,
        help="type2 매수 전 확인할 연속 + 일수 (기본값: 33)",
    )
    parser.add_argument(
        "--minus_days",
        type=int,
        default=5,
        help="type2 매도 전 확인할 연속 - 일수 (기본값: 5)",
    )
    parser.add_argument(
        "--krw_capital",
        type=float,
        default=10_000_000,
        help="KOSPI 200 종목당 초기자금 KRW (기본값: 10000000)",
    )
    parser.add_argument(
        "--usd_capital",
        type=float,
        default=10_000,
        help="S&P500 / ETF 종목당 초기자금 USD (기본값: 10000)",
    )
    parser.add_argument(
        "--output_csv",
        dest="output_csv",
        default=default_output_csv(),
        help="결과 CSV 저장 경로 (기본값: backtest_compare.csv)",
    )
    args = parser.parse_args()
    if args.plus_days < 1 or args.minus_days < 1:
        raise ValueError("--plus_days 와 --minus_days 는 1 이상이어야 합니다.")
    if args.krw_capital <= 0 or args.usd_capital <= 0:
        raise ValueError("초기자금은 0보다 커야 합니다.")
    return args


def empty_result(initial_capital: float, status: str) -> CapitalResult:
    return CapitalResult(
        shares_held=0,
        cash=round(initial_capital, 2),
        total_asset=round(initial_capital, 2),
        profit=0.0,
        return_pct=0.0,
        buy_count=0,
        sell_count=0,
        last_buy_date="-",
        last_sell_date="-",
        holding_status=status,
    )


def prepare_signal_frame(df: pd.DataFrame, window: BacktestWindow) -> tuple[pd.DataFrame, pd.DataFrame]:
    start_ts = pd.Timestamp(window.start)
    end_ts = pd.Timestamp(window.end)
    period_df = df.loc[(df.index >= start_ts) & (df.index <= end_ts)].copy()
    previous_row = df.loc[df.index < start_ts].tail(1)
    signal_df = pd.concat([previous_row, period_df]) if not previous_row.empty else period_df
    signal_df = signal_df.dropna(subset=["MA10M"])
    return period_df, signal_df


def buy_all(cash: float, price: float) -> tuple[int, float, float]:
    shares = int(cash // price)
    spent = shares * price
    return shares, spent, cash - spent


def simulate_type1_capital(df: pd.DataFrame, window: BacktestWindow, initial_capital: float) -> CapitalResult:
    period_df, signal_df = prepare_signal_frame(df, window)
    if period_df.empty:
        return empty_result(initial_capital, "기간 데이터 없음")
    if len(signal_df) < 2:
        return empty_result(initial_capital, "신호 없음")

    valuation_price = float(period_df["Close"].iloc[-1])
    start_ts = pd.Timestamp(window.start)
    end_ts = pd.Timestamp(window.end)
    is_positive = signal_df["Close"] > signal_df["MA10M"]

    cash = initial_capital
    shares_held = 0
    buy_count = 0
    sell_count = 0
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
            shares, spent, remaining_cash = buy_all(cash, trade_price)
            if shares > 0:
                shares_held = shares
                cash = remaining_cash
                buy_count += 1
                last_buy_date = trade_date.strftime("%Y-%m-%d")
        elif prev_positive and not curr_positive and shares_held > 0:
            cash += shares_held * trade_price
            shares_held = 0
            sell_count += 1
            last_sell_date = trade_date.strftime("%Y-%m-%d")

    total_asset = cash + shares_held * valuation_price
    profit = total_asset - initial_capital
    holding_status = "보유중(기간 종료가 평가)" if shares_held else "미보유"
    if buy_count == 0:
        holding_status = "매수 없음"

    return CapitalResult(
        shares_held=shares_held,
        cash=round(cash, 2),
        total_asset=round(total_asset, 2),
        profit=round(profit, 2),
        return_pct=round((profit / initial_capital) * 100, 2),
        buy_count=buy_count,
        sell_count=sell_count,
        last_buy_date=last_buy_date,
        last_sell_date=last_sell_date,
        holding_status=holding_status,
    )


def simulate_type2_capital(
    df: pd.DataFrame,
    window: BacktestWindow,
    initial_capital: float,
    plus_days: int,
    minus_days: int,
) -> CapitalResult:
    period_df, signal_df = prepare_signal_frame(df, window)
    if period_df.empty:
        return empty_result(initial_capital, "기간 데이터 없음")
    if len(signal_df) < 2:
        return empty_result(initial_capital, "신호 없음")

    valuation_price = float(period_df["Close"].iloc[-1])
    start_ts = pd.Timestamp(window.start)
    end_ts = pd.Timestamp(window.end)
    is_positive = signal_df["Close"] > signal_df["MA10M"]

    cash = initial_capital
    shares_held = 0
    buy_count = 0
    sell_count = 0
    positive_streak = 0
    negative_streak = 0
    last_buy_date = "-"
    last_sell_date = "-"

    for i in range(1, len(signal_df)):
        trade_date = signal_df.index[i]
        if trade_date < start_ts or trade_date > end_ts:
            continue
        prev_positive = bool(is_positive.iloc[i - 1])
        curr_positive = bool(is_positive.iloc[i])
        trade_price = float(signal_df["Close"].iloc[i])

        if curr_positive:
            negative_streak = 0
            if not prev_positive:
                positive_streak = 1
            elif positive_streak > 0:
                positive_streak += 1

            if shares_held == 0 and positive_streak == plus_days:
                shares, spent, remaining_cash = buy_all(cash, trade_price)
                if shares > 0:
                    shares_held = shares
                    cash = remaining_cash
                    buy_count += 1
                    last_buy_date = trade_date.strftime("%Y-%m-%d")
        else:
            positive_streak = 0
            if prev_positive:
                negative_streak = 1
            elif negative_streak > 0:
                negative_streak += 1

            if shares_held > 0 and negative_streak == minus_days:
                cash += shares_held * trade_price
                shares_held = 0
                sell_count += 1
                last_sell_date = trade_date.strftime("%Y-%m-%d")

    total_asset = cash + shares_held * valuation_price
    profit = total_asset - initial_capital
    holding_status = "보유중(기간 종료가 평가)" if shares_held else "미보유"
    if buy_count == 0:
        holding_status = "매수 없음"

    return CapitalResult(
        shares_held=shares_held,
        cash=round(cash, 2),
        total_asset=round(total_asset, 2),
        profit=round(profit, 2),
        return_pct=round((profit / initial_capital) * 100, 2),
        buy_count=buy_count,
        sell_count=sell_count,
        last_buy_date=last_buy_date,
        last_sell_date=last_sell_date,
        holding_status=holding_status,
    )


def generate_quarterly_dates(start_ts: pd.Timestamp, end_ts: pd.Timestamp) -> list[pd.Timestamp]:
    dates: list[pd.Timestamp] = []
    current = start_ts.normalize()
    while current <= end_ts:
        dates.append(current)
        current = current + pd.DateOffset(months=3)
    return dates


def first_trading_day_on_or_after(index: pd.Index, target: pd.Timestamp) -> pd.Timestamp | None:
    later = index[index >= target]
    if len(later) == 0:
        return None
    return pd.Timestamp(later[0])


def simulate_type3_quarterly_dca(df: pd.DataFrame, window: BacktestWindow, initial_capital: float) -> CapitalResult:
    period_df = df.loc[(df.index >= pd.Timestamp(window.start)) & (df.index <= pd.Timestamp(window.end))].copy()
    if period_df.empty:
        return empty_result(initial_capital, "기간 데이터 없음")

    schedule_dates = generate_quarterly_dates(pd.Timestamp(window.start), pd.Timestamp(window.end))
    tranche = initial_capital / len(schedule_dates)

    cash = 0.0
    shares_held = 0
    buy_count = 0
    last_buy_date = "-"
    used_trade_dates: set[pd.Timestamp] = set()

    for schedule_date in schedule_dates:
        cash += tranche
        trade_date = first_trading_day_on_or_after(period_df.index, schedule_date)
        if trade_date is None:
            continue
        if trade_date in used_trade_dates:
            continue
        trade_price = float(period_df.loc[trade_date, "Close"])
        shares, spent, remaining_cash = buy_all(cash, trade_price)
        if shares > 0:
            shares_held += shares
            cash = remaining_cash
            buy_count += 1
            last_buy_date = trade_date.strftime("%Y-%m-%d")
            used_trade_dates.add(trade_date)

    valuation_price = float(period_df["Close"].iloc[-1])
    total_asset = cash + shares_held * valuation_price
    profit = total_asset - initial_capital
    holding_status = "적립식 보유중" if shares_held else "매수 없음"

    return CapitalResult(
        shares_held=shares_held,
        cash=round(cash, 2),
        total_asset=round(total_asset, 2),
        profit=round(profit, 2),
        return_pct=round((profit / initial_capital) * 100, 2),
        buy_count=buy_count,
        sell_count=0,
        last_buy_date=last_buy_date,
        last_sell_date="-",
        holding_status=holding_status,
    )


def summary_row(df: pd.DataFrame, group_name: str, initial_capital: float, type4_initial_capital: float | None) -> dict:
    count = max(len(df), 1)
    total_initial = initial_capital * count
    row = {column: "" for column in df.columns}
    row["그룹"] = group_name
    row["티커"] = "합계"
    row["종목명"] = f"{group_name} 합계"
    row["통화"] = df["통화"].iloc[0]
    row["초기자금"] = round(total_initial, 2)
    row["type4_초기자금"] = round(type4_initial_capital * count, 2) if type4_initial_capital is not None else ""
    for prefix in ["type1", "type2", "type3"]:
        total_asset = float(df[f"{prefix}_총자산"].sum())
        total_profit = float(df[f"{prefix}_손익"].sum())
        row[f"{prefix}_현금"] = round(float(df[f"{prefix}_현금"].sum()), 2)
        row[f"{prefix}_총자산"] = round(total_asset, 2)
        row[f"{prefix}_손익"] = round(total_profit, 2)
        row[f"{prefix}_수익률(%)"] = round((total_profit / total_initial) * 100, 2) if total_initial else 0.0
        row[f"{prefix}_매수횟수"] = int(df[f"{prefix}_매수횟수"].sum())
        row[f"{prefix}_매도횟수"] = int(df[f"{prefix}_매도횟수"].sum())
    if group_name == "ETF":
        for prefix in ["type4", "type4_2"]:
            row[f"{prefix}_현금잔고" if "2" in prefix else f"{prefix}_현금"] = ""
            row[f"{prefix}_총자산"] = ""
            row[f"{prefix}_손익"] = ""
            row[f"{prefix}_수익률(%)"] = ""
            row[f"{prefix}_매수횟수"] = ""
            row[f"{prefix}_매도횟수"] = ""
        row["type4_2_초기자본"] = ""
    else:
        total_asset = float(df["type4_총자산"].sum())
        total_profit = float(df["type4_손익"].sum())
        type4_total_initial = (type4_initial_capital or 0.0) * count
        row["type4_현금"] = round(float(df["type4_현금"].sum()), 2)
        row["type4_총자산"] = round(total_asset, 2)
        row["type4_손익"] = round(total_profit, 2)
        row["type4_수익률(%)"] = round((total_profit / type4_total_initial) * 100, 2) if type4_total_initial else 0.0
        row["type4_매수횟수"] = int(df["type4_매수횟수"].sum())
        row["type4_매도횟수"] = int(df["type4_매도횟수"].sum())
        # type4_2: 초기자본이 종목마다 다르므로 합산
        t42_initial = float(df["type4_2_초기자본"].replace("", 0).apply(pd.to_numeric, args=("coerce",)).fillna(0).sum()) if "type4_2_초기자본" in df.columns else 0.0
        t42_profit = float(df["type4_2_손익"].replace("", 0).apply(pd.to_numeric, args=("coerce",)).fillna(0).sum())
        row["type4_2_현금잔고"] = round(float(df["type4_2_현금잔고"].replace("", 0).apply(pd.to_numeric, args=("coerce",)).fillna(0).sum()), 2)
        row["type4_2_초기자본"] = round(t42_initial, 2)
        row["type4_2_총자산"] = round(float(df["type4_2_총자산"].replace("", 0).apply(pd.to_numeric, args=("coerce",)).fillna(0).sum()), 2)
        row["type4_2_손익"] = round(t42_profit, 2)
        row["type4_2_수익률(%)"] = round((t42_profit / t42_initial) * 100, 2) if t42_initial else 0.0
        row["type4_2_매수횟수"] = int(df["type4_2_매수횟수"].replace("", 0).apply(pd.to_numeric, args=("coerce",)).fillna(0).sum())
        row["type4_2_매도횟수"] = int(df["type4_2_매도횟수"].replace("", 0).apply(pd.to_numeric, args=("coerce",)).fillna(0).sum())
    # type1_2: 초기자본이 종목마다 다르므로 합산
    t12_initial = float(df["type1_2_초기자본"].replace("", 0).apply(pd.to_numeric, args=("coerce",)).fillna(0).sum())
    t12_profit = float(df["type1_2_손익"].replace("", 0).apply(pd.to_numeric, args=("coerce",)).fillna(0).sum())
    row["type1_2_현금잔고"] = round(float(df["type1_2_현금잔고"].replace("", 0).apply(pd.to_numeric, args=("coerce",)).fillna(0).sum()), 2)
    row["type1_2_초기자본"] = round(t12_initial, 2)
    row["type1_2_총자산"] = round(float(df["type1_2_총자산"].replace("", 0).apply(pd.to_numeric, args=("coerce",)).fillna(0).sum()), 2)
    row["type1_2_손익"] = round(t12_profit, 2)
    row["type1_2_수익률(%)"] = round((t12_profit / t12_initial) * 100, 2) if t12_initial else 0.0
    row["type1_2_매수횟수"] = int(df["type1_2_매수횟수"].replace("", 0).apply(pd.to_numeric, args=("coerce",)).fillna(0).sum())
    row["type1_2_매도횟수"] = int(df["type1_2_매도횟수"].replace("", 0).apply(pd.to_numeric, args=("coerce",)).fillna(0).sum())
    return row


def format_number(value):
    if value == "" or pd.isna(value):
        return ""
    number = float(value)
    return int(number) if number.is_integer() else round(number, 2)


def print_group_result(group_name: str, window: BacktestWindow, df: pd.DataFrame) -> None:
    bar = "=" * 160
    print(f"\n{bar}")
    print(f"[{window.title}] {group_name} 동일 초기자금 비교")
    print(bar)
    if df.empty:
        print("  결과 없음")
        return

    display_df = df.copy()
    if len(display_df) > 21:
        display_df = pd.concat([display_df.head(20), display_df.tail(1)], ignore_index=True)
    numeric_cols = [
        "초기자금",
        "type4_초기자금",
        "평가종가",
        "평가거래량",
        "20일평균거래량",
        "거래량배수",
        "type1_보유주식수",
        "type1_현금",
        "type1_총자산",
        "type1_손익",
        "type1_수익률(%)",
        "type1_매수횟수",
        "type1_매도횟수",
        "type2_보유주식수",
        "type2_현금",
        "type2_총자산",
        "type2_손익",
        "type2_수익률(%)",
        "type2_매수횟수",
        "type2_매도횟수",
        "type3_보유주식수",
        "type3_현금",
        "type3_총자산",
        "type3_손익",
        "type3_수익률(%)",
        "type3_매수횟수",
        "type3_매도횟수",
        "type4_보유주식수",
        "type4_현금",
        "type4_총자산",
        "type4_손익",
        "type4_수익률(%)",
        "type4_매수횟수",
        "type4_매도횟수",
        "type1_2_보유주식수",
        "type1_2_현금잔고",
        "type1_2_초기자본",
        "type1_2_총자산",
        "type1_2_손익",
        "type1_2_수익률(%)",
        "type1_2_매수횟수",
        "type1_2_매도횟수",
        "type4_2_보유주식수",
        "type4_2_현금잔고",
        "type4_2_초기자본",
        "type4_2_총자산",
        "type4_2_손익",
        "type4_2_수익률(%)",
        "type4_2_매수횟수",
        "type4_2_매도횟수",
    ]
    for col in numeric_cols:
        display_df[col] = display_df[col].map(format_number)

    right_cols = set(numeric_cols) | {"최고전략_매수일_시총순위"}
    print_table(display_df, right_cols=right_cols)


def save_result(output_csv: str, dfs: list[pd.DataFrame]) -> Path | None:
    frames = [df for df in dfs if not df.empty]
    if not frames:
        return None
    result_df = pd.concat(frames, ignore_index=True)
    output_path = Path(output_csv)
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result_df.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path


def build_group_result(
    group_name: str,
    items: list[dict],
    window: BacktestWindow,
    initial_capital: float,
    type4_initial_capital: float | None,
    currency: str,
    plus_days: int,
    minus_days: int,
    rank_contexts: dict,
) -> pd.DataFrame:
    rows: list[dict] = []
    rank_table = load_rank_table(group_name)
    for item in items:
        df = load_price_frame(item["stocks_dir"] / f"{item['ticker']}.csv")
        if df is None:
            continue

        period_df = df.loc[(df.index >= pd.Timestamp(window.start)) & (df.index <= pd.Timestamp(window.end))].copy()
        if period_df.empty:
            continue

        type1 = simulate_type1_capital(df, window, initial_capital)
        type2 = simulate_type2_capital(df, window, initial_capital, plus_days, minus_days)
        type3 = simulate_type3_quarterly_dca(df, window, initial_capital)
        type4 = simulate_type4_capital(
            df=df,
            window=window,
            initial_capital=type4_initial_capital or initial_capital,
            group_name=group_name,
            ticker=str(item["ticker"]),
            rank_context=rank_contexts.get(group_name),
        )
        r12 = simulate_type1_2(df, window)
        r42 = simulate_type4_2(df, window, group_name, str(item["ticker"]), rank_contexts.get(group_name))
        volume_metrics = compute_volume_metrics(period_df)
        valuation_price = float(period_df["Close"].iloc[-1])
        valuation_date = period_df.index[-1].strftime("%Y-%m-%d")

        # type1_2/type4_2: total_asset = cash + shares * valuation_price
        r12_total_asset = r12["cash"] + r12["shares_held"] * valuation_price
        r42_total_asset = r42["cash"] + r42["shares_held"] * valuation_price if r42["initial_capital"] > 0 else 0.0

        best_strategy = max(
            [
                ("type1", type1.total_asset),
                ("type2", type2.total_asset),
                ("type3", type3.total_asset),
                ("type4", type4["total_asset"]),
                ("type1_2", r12_total_asset),
                ("type4_2", r42_total_asset),
            ],
            key=lambda x: x[1],
        )[0]

        best_results = {
            "type1": (type1.shares_held, type1.last_buy_date),
            "type2": (type2.shares_held, type2.last_buy_date),
            "type3": (type3.shares_held, type3.last_buy_date),
            "type4": (type4["shares_held"], type4["last_buy_date"]),
            "type1_2": (r12["shares_held"], r12["last_buy_date"]),
            "type4_2": (r42["shares_held"], r42["last_buy_date"]),
        }
        best_shares_held, best_last_buy_date = best_results[best_strategy]
        ticker_str = str(item["ticker"])
        rank_str = (
            get_rank_at_date(rank_table, ticker_str, best_last_buy_date)
            if best_shares_held > 0 and best_last_buy_date != "-"
            else "-"
        )

        rows.append(
            {
                "그룹": group_name,
                "티커": item["ticker"],
                "종목명": item["name"],
                "통화": currency,
                "초기자금": round(initial_capital, 2),
                "type4_초기자금": round(type4_initial_capital, 2) if type4_initial_capital is not None else "",
                "평가종가": round(valuation_price, 2),
                "평가가격일": valuation_date,
                "평가거래량": volume_metrics["current_volume"],
                "20일평균거래량": volume_metrics["avg_volume_20d"],
                "거래량배수": volume_metrics["volume_ratio_20d"],
                "type1_상태": type1.holding_status,
                "type1_보유주식수": type1.shares_held,
                "type1_현금": type1.cash,
                "type1_총자산": type1.total_asset,
                "type1_손익": type1.profit,
                "type1_수익률(%)": type1.return_pct,
                "type1_매수횟수": type1.buy_count,
                "type1_매도횟수": type1.sell_count,
                "type2_상태": type2.holding_status,
                "type2_보유주식수": type2.shares_held,
                "type2_현금": type2.cash,
                "type2_총자산": type2.total_asset,
                "type2_손익": type2.profit,
                "type2_수익률(%)": type2.return_pct,
                "type2_매수횟수": type2.buy_count,
                "type2_매도횟수": type2.sell_count,
                "type3_상태": type3.holding_status,
                "type3_보유주식수": type3.shares_held,
                "type3_현금": type3.cash,
                "type3_총자산": type3.total_asset,
                "type3_손익": type3.profit,
                "type3_수익률(%)": type3.return_pct,
                "type3_매수횟수": type3.buy_count,
                "type3_매도횟수": type3.sell_count,
                "type4_상태": type4["holding_status"],
                "type4_보유주식수": type4["shares_held"],
                "type4_현금": type4["cash"],
                "type4_총자산": type4["total_asset"],
                "type4_손익": type4["profit"],
                "type4_수익률(%)": type4["return_pct"],
                "type4_매수횟수": type4["buy_count"],
                "type4_매도횟수": type4["sell_count"],
                "type1_2_상태": r12["holding_status"],
                "type1_2_보유주식수": r12["shares_held"],
                "type1_2_현금잔고": r12["cash"],
                "type1_2_초기자본": r12["initial_capital"],
                "type1_2_총자산": round(r12_total_asset, 2),
                "type1_2_손익": r12["total_profit"],
                "type1_2_수익률(%)": r12["return_pct"],
                "type1_2_매수횟수": r12["buy_count"],
                "type1_2_매도횟수": r12["sell_count"],
                "type4_2_상태": r42["holding_status"],
                "type4_2_보유주식수": r42["shares_held"],
                "type4_2_현금잔고": r42["cash"],
                "type4_2_초기자본": r42["initial_capital"],
                "type4_2_총자산": round(r42_total_asset, 2),
                "type4_2_손익": r42["total_profit"],
                "type4_2_수익률(%)": r42["return_pct"],
                "type4_2_매수횟수": r42["buy_count"],
                "type4_2_매도횟수": r42["sell_count"],
                "최고전략": best_strategy,
                "최고전략_매수일_시총순위": rank_str,
            }
        )

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).sort_values(
        by=["type2_총자산", "type1_총자산", "type3_총자산", "티커"],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)
    return pd.concat([df, pd.DataFrame([summary_row(df, group_name, initial_capital, type4_initial_capital)])], ignore_index=True)


def main() -> None:
    args = parse_args()
    window = build_window(args.from_date, args.to_date)

    print("동일 초기자금 기준 type1 / type2 / type3 비교를 시작합니다...")
    print(f"기준일: {datetime.now().strftime('%Y-%m-%d')}")
    print(f"기간: {window.title}")
    print(f"type2 규칙: + {args.plus_days}일 / - {args.minus_days}일 확인")
    print("type3 규칙: 신호와 무관하게 3개월마다 동일 금액 적립식 매수 후 보유")
    print(
        "type4 규칙: KOSPI 상위 30 / S&P500 상위 100 시가총액 조건을 만족하는 + 신호만 매수 "
        f"(type4 초기자금: KOSPI={args.krw_capital / KOSPI_TOP_N:.2f}, "
        f"S&P500={args.usd_capital / SP500_TOP_N:.2f})"
    )

    rank_contexts = build_rank_contexts()
    group_results: list[pd.DataFrame] = []
    for group_name, items in build_universe():
        currency = "KRW" if group_name == "KOSPI 200" else "USD"
        initial_capital = args.krw_capital if group_name == "KOSPI 200" else args.usd_capital
        slot_count = type4_slot_count(group_name)
        type4_initial_capital = (initial_capital / slot_count) if slot_count else None
        df = build_group_result(
            group_name=group_name,
            items=items,
            window=window,
            initial_capital=initial_capital,
            type4_initial_capital=type4_initial_capital,
            currency=currency,
            plus_days=args.plus_days,
            minus_days=args.minus_days,
            rank_contexts=rank_contexts,
        )
        group_results.append(df)
        print_group_result(group_name, window, df)

    output_path = save_result(args.output_csv, group_results)
    if output_path:
        print(f"\n→ CSV 저장: {output_path}")


if __name__ == "__main__":
    main()
