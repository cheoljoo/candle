"""
backtest_type2.py

Type2 규칙:
  - 종가가 10월이평(MA10M) 아래(-)에서 위(+)로 바뀐 뒤, `--plus_days`일 연속 +가 유지되면 10주 매수
  - 종가가 10월이평 위(+)에서 아래(-)로 바뀐 뒤, `--minus_days`일 연속 -가 유지되면 보유 10주 전량 매도
  - 매매 가격은 조건을 충족한 당일 종가를 사용
  - 기간 종료 시 아직 매도 신호가 없으면 `--to` 기준 평가가격으로 손익 계산
  - 거래량이 저장되어 있으면 평가일 거래량, 최근 20일 평균 거래량, 거래량 배수를 함께 출력
"""

from __future__ import annotations

import argparse
from datetime import datetime
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
    default_to_date,
    get_rank_at_date,
    load_price_frame,
    load_rank_table,
    save_window_result,
)


def default_output_csv() -> str:
    return "backtest_type2.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Type2 백테스트: -→+ 직후 즉시 매수하지 않고 +가 연속으로 유지된 뒤 매수하며, "
            "+→- 직후 즉시 매도하지 않고 -가 연속으로 유지된 뒤 매도합니다. "
            "저장된 거래량이 있으면 평가 시점 거래량 지표도 함께 보여줍니다."
        ),
        epilog=(
            "예시:\n"
            "  uv run python backtest_type2.py\n"
            "  uv run python backtest_type2.py --plus_days 3 --minus_days 2\n"
            "  uv run python backtest_type2.py --from 2024-01-01 --to 2026-04-11 "
            "--plus_days 5 --minus_days 3 --output_csv data/backtest_type2.csv"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--from",
        dest="from_date",
        default=default_from_date(),
        help="백테스트 시작일 (YYYY-MM-DD, 기본값: 2년 전 01-01)",
    )
    parser.add_argument(
        "--to",
        dest="to_date",
        default=default_to_date(),
        help="백테스트 종료일이자 평가 기준일 (YYYY-MM-DD, 기본값: 오늘)",
    )
    parser.add_argument(
        "--plus_days",
        type=int,
        default=1,
        help="-→+ 전환 후 매수까지 기다릴 연속 + 일수 (기본값: 1)",
    )
    parser.add_argument(
        "--minus_days",
        type=int,
        default=1,
        help="+→- 전환 후 매도까지 기다릴 연속 - 일수 (기본값: 1)",
    )
    parser.add_argument(
        "--output_csv",
        dest="output_csv",
        default=default_output_csv(),
        help="결과 CSV 저장 경로 (기본값: backtest_type2.csv)",
    )
    args = parser.parse_args()
    if args.plus_days < 1 or args.minus_days < 1:
        raise ValueError("--plus_days 와 --minus_days 는 1 이상이어야 합니다.")
    return args


def empty_result(window: BacktestWindow, current_price: float, current_date: str, price_date: str, status: str) -> dict:
    return {
        "period": window.title,
        "period_start": window.start,
        "period_end": window.end,
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
        "current_volume": None,
        "avg_volume_20d": None,
        "volume_ratio_20d": None,
    }


def compute_volume_metrics(period_df: pd.DataFrame) -> dict:
    if "Volume" not in period_df.columns:
        return {
            "current_volume": None,
            "avg_volume_20d": None,
            "volume_ratio_20d": None,
        }

    volume = pd.to_numeric(period_df["Volume"], errors="coerce").dropna()
    if volume.empty:
        return {
            "current_volume": None,
            "avg_volume_20d": None,
            "volume_ratio_20d": None,
        }

    current_volume = float(volume.iloc[-1])
    avg_volume_20d = float(volume.tail(20).mean())
    volume_ratio_20d = (current_volume / avg_volume_20d) if avg_volume_20d else None
    return {
        "current_volume": round(current_volume, 2),
        "avg_volume_20d": round(avg_volume_20d, 2),
        "volume_ratio_20d": round(volume_ratio_20d, 2) if volume_ratio_20d is not None else None,
    }


def simulate_type2(df: pd.DataFrame, window: BacktestWindow, plus_days: int, minus_days: int) -> dict:
    start_ts = pd.Timestamp(window.start)
    end_ts = pd.Timestamp(window.end)
    period_df = df.loc[(df.index >= start_ts) & (df.index <= end_ts)].copy()
    previous_row = df.loc[df.index < start_ts].tail(1)

    if period_df.empty:
        return empty_result(window, 0.0, window.end, "-", "기간 데이터 없음")

    signal_df = pd.concat([previous_row, period_df]) if not previous_row.empty else period_df
    signal_df = signal_df.dropna(subset=["MA10M"])
    if len(signal_df) < 2:
        return empty_result(
            window,
            float(period_df["Close"].iloc[-1]),
            window.end,
            period_df.index[-1].strftime("%Y-%m-%d"),
            "신호 없음",
        )

    valuation_price = float(period_df["Close"].iloc[-1])
    valuation_price_date = period_df.index[-1]
    volume_metrics = compute_volume_metrics(period_df)

    shares_held = 0
    buy_count = 0
    sell_count = 0
    total_buy_amount = 0.0
    closed_buy_amount = 0.0
    realized_profit = 0.0
    entry_cost = 0.0
    last_buy_date = "-"
    last_sell_date = "-"

    is_positive = signal_df["Close"] > signal_df["MA10M"]
    positive_streak = 0
    negative_streak = 0

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
                shares_held = SHARES_PER_TRADE
                entry_cost = trade_price * SHARES_PER_TRADE
                total_buy_amount += entry_cost
                buy_count += 1
                last_buy_date = trade_date.strftime("%Y-%m-%d")
        else:
            positive_streak = 0
            if prev_positive:
                negative_streak = 1
            elif negative_streak > 0:
                negative_streak += 1

            if shares_held > 0 and negative_streak == minus_days:
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
        "period_start": window.start,
        "period_end": window.end,
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
        **volume_metrics,
    }


def run_group_backtest(group_name: str, items: list[dict], window: BacktestWindow, plus_days: int, minus_days: int) -> pd.DataFrame:
    rows: list[dict] = []
    rank_table = load_rank_table(group_name)

    for item in items:
        df = load_price_frame(item["stocks_dir"] / f"{item['ticker']}.csv")
        if df is None:
            continue

        result = simulate_type2(df, window, plus_days, minus_days)
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
                "평가거래량": result["current_volume"],
                "20일평균거래량": result["avg_volume_20d"],
                "거래량배수": result["volume_ratio_20d"],
                "마지막매수일": result["last_buy_date"],
                "매수일_시총순위": rank_str,
                "마지막매도일": result["last_sell_date"],
            }
        )

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.sort_values(
        by=["수익률(%)", "총손익", "티커"],
        ascending=[False, False, True],
    ).reset_index(drop=True)
    return append_group_summary(df, group_name)


def print_group_result(group_name: str, window: BacktestWindow, df: pd.DataFrame) -> None:
    bar = "=" * 140
    print(f"\n{bar}")
    print(f"[{window.title}] {group_name} Type2 백테스트")
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
    for column in [
        "평가종가",
        "총매수금액",
        "사고판수익",
        "사고판수익률(%)",
        "실현손익",
        "미실현손익",
        "총손익",
        "수익률(%)",
        "평가거래량",
        "20일평균거래량",
        "거래량배수",
    ]:
        display_df[column] = display_df[column].map(format_number)

    right_cols = {
        "평가종가",
        "보유주식수",
        "매수횟수",
        "매도횟수",
        "총매수금액",
        "사고판수익",
        "사고판수익률(%)",
        "실현손익",
        "미실현손익",
        "총손익",
        "수익률(%)",
        "평가거래량",
        "20일평균거래량",
        "거래량배수",
        "매수일_시총순위",
    }
    print_table(display_df, right_cols=right_cols)


def main() -> None:
    args = parse_args()
    window = build_window(args.from_date, args.to_date)

    print("Type2 백테스트를 시작합니다...")
    print(f"기준일: {datetime.now().strftime('%Y-%m-%d')}")
    print(f"기간: {window.title}")
    print(
        "규칙: -→+ 직후 즉시 매수하지 않고 "
        f"+ {args.plus_days}일 연속 확인 후 10주 매수 / "
        f"+→- 직후 즉시 매도하지 않고 - {args.minus_days}일 연속 확인 후 전량 매도"
    )

    universe = build_universe()
    group_results: list[pd.DataFrame] = []
    for group_name, items in universe:
        df = run_group_backtest(group_name, items, window, args.plus_days, args.minus_days)
        group_results.append(df)
        print_group_result(group_name, window, df)

    output_path = save_window_result(args.output_csv, group_results)
    if output_path:
        print(f"\n→ CSV 저장: {output_path}")


if __name__ == "__main__":
    main()
