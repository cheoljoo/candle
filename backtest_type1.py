"""
backtest_type1.py

Type1 규칙:
  - 10월이평(MA10M) 대비 종가가 -→+ 로 바뀌면 10주 매수
  - +→- 로 바뀌면 보유 10주 전량 매도
  - 매매 가격은 신호가 발생한 당일 종가를 사용
  - 기간 종료 시 아직 매도 신호가 없으면 `--to` 기준 평가가격으로 손익 계산

CLI:
  --from       백테스트 시작일 (기본값: 올해 01-01)
  --to         백테스트 종료일/평가 기준일 (기본값: 오늘)
  --output_csv 결과 CSV 저장 경로 (기본값: backtest_type1.csv)
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from analyze import (
    DATA_DIR,
    ETF_SYMBOLS,
    STOCKS_DIR,
    US_STOCKS_DIR,
    format_marcap,
    load_kospi_list,
    load_sp500_list,
    print_table,
)
from fetch_data import compute_ma10m

SHARES_PER_TRADE = 10


@dataclass(frozen=True)
class BacktestWindow:
    title: str
    start: str
    end: str


def default_from_date() -> str:
    today = date.today()
    return f"{today.year - 2}-01-01"


def default_to_date() -> str:
    return date.today().isoformat()


def default_output_csv() -> str:
    return "backtest_type1.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Type1 백테스트: MA10M 아래(-)에서 위(+)로 바뀌면 10주 매수하고, "
            "위(+)에서 아래(-)로 바뀌면 보유 10주를 전량 매도합니다. "
            "평가 기준일은 항상 --to 날짜입니다."
        ),
        epilog=(
            "예시:\n"
            "  uv run python backtest_type1.py\n"
            "  uv run python backtest_type1.py --from 2020-01-01 --to 2025-12-31 "
            "--output_csv data/backtest_type1_2020_2025.csv\n"
            "  uv run python backtest_type1.py --from 2025-01-01 --to 2026-04-11 "
            "--output_csv data/backtest_type1_2025_now.csv"
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
        "--output_csv",
        dest="output_csv",
        default=default_output_csv(),
        help="결과 CSV 저장 경로 (기본값: backtest_type1.csv)",
    )
    return parser.parse_args()


def build_window(from_date: str, to_date: str) -> BacktestWindow:
    start_ts = pd.Timestamp(from_date)
    end_ts = pd.Timestamp(to_date)
    if end_ts < start_ts:
        raise ValueError("--to 는 --from 보다 빠를 수 없습니다.")
    return BacktestWindow(
        title=f"{start_ts.strftime('%Y-%m-%d')} ~ {end_ts.strftime('%Y-%m-%d')}",
        start=start_ts.strftime("%Y-%m-%d"),
        end=end_ts.strftime("%Y-%m-%d"),
    )


def load_price_frame(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None

    df = pd.read_csv(path, index_col=0, parse_dates=True)
    if df.empty or "Close" not in df.columns:
        return None

    close = pd.to_numeric(df["Close"], errors="coerce")
    ma10m = (
        pd.to_numeric(df["MA10M"], errors="coerce")
        if "MA10M" in df.columns
        else compute_ma10m(close)
    )

    price_df = pd.DataFrame({"Close": close, "MA10M": ma10m}).dropna(subset=["Close"])
    if price_df.empty:
        return None

    return price_df.sort_index()


def simulate_type1(df: pd.DataFrame, window: BacktestWindow) -> dict:
    start_ts = pd.Timestamp(window.start)
    end_ts = pd.Timestamp(window.end)
    period_df = df.loc[(df.index >= start_ts) & (df.index <= end_ts)].copy()
    previous_row = df.loc[df.index < start_ts].tail(1)

    if period_df.empty:
        return {
            "period": window.title,
            "period_start": window.start,
            "period_end": end_ts.strftime("%Y-%m-%d"),
            "current_price": 0.0,
            "current_date": end_ts.strftime("%Y-%m-%d"),
            "price_date": "-",
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
            "holding_status": "기간 데이터 없음",
            "last_buy_date": "-",
            "last_sell_date": "-",
        }

    signal_df = pd.concat([previous_row, period_df]) if not previous_row.empty else period_df
    signal_df = signal_df.dropna(subset=["MA10M"])
    if len(signal_df) < 2:
        return {
            "period": window.title,
            "period_start": window.start,
            "period_end": end_ts.strftime("%Y-%m-%d"),
            "current_price": round(float(period_df["Close"].iloc[-1]), 2),
            "current_date": end_ts.strftime("%Y-%m-%d"),
            "price_date": period_df.index[-1].strftime("%Y-%m-%d"),
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
            "holding_status": "신호 없음",
            "last_buy_date": "-",
            "last_sell_date": "-",
        }

    valuation_price = float(period_df["Close"].iloc[-1])
    valuation_price_date = period_df.index[-1]
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

    for i in range(1, len(signal_df)):
        trade_date = signal_df.index[i]
        if trade_date < start_ts or trade_date > end_ts:
            continue

        prev_positive = bool(is_positive.iloc[i - 1])
        curr_positive = bool(is_positive.iloc[i])
        trade_price = float(signal_df["Close"].iloc[i])

        if not prev_positive and curr_positive and shares_held == 0:
            shares_held = SHARES_PER_TRADE
            entry_cost = trade_price * SHARES_PER_TRADE
            total_buy_amount += entry_cost
            buy_count += 1
            last_buy_date = trade_date.strftime("%Y-%m-%d")
        elif prev_positive and not curr_positive and shares_held > 0:
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
        "period_end": end_ts.strftime("%Y-%m-%d"),
        "current_price": round(valuation_price, 2),
        "current_date": end_ts.strftime("%Y-%m-%d"),
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


def build_universe() -> list[tuple[str, list[dict]]]:
    kospi_df = load_kospi_list()
    sp500_df = load_sp500_list()

    return [
        (
            "KOSPI 200",
            [
                {
                    "ticker": str(row["Code"]),
                    "name": str(row["Name"]),
                    "stocks_dir": STOCKS_DIR,
                    "marcap": format_marcap(row.get("Marcap", 0)),
                }
                for _, row in kospi_df.head(200).iterrows()
            ],
        ),
        (
            "S&P500",
            [
                {
                    "ticker": str(row["Symbol"]),
                    "name": str(row["Name"]),
                    "stocks_dir": US_STOCKS_DIR,
                    "marcap": "-",
                }
                for _, row in sp500_df.iterrows()
            ],
        ),
        (
            "ETF",
            [
                {
                    "ticker": symbol,
                    "name": symbol,
                    "stocks_dir": US_STOCKS_DIR,
                    "marcap": "-",
                }
                for symbol in ETF_SYMBOLS
            ],
        ),
    ]


def run_group_backtest(group_name: str, items: list[dict], window: BacktestWindow) -> pd.DataFrame:
    rows: list[dict] = []

    for item in items:
        df = load_price_frame(item["stocks_dir"] / f"{item['ticker']}.csv")
        if df is None:
            continue

        result = simulate_type1(df, window)
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
                "마지막매수일": result["last_buy_date"],
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


def append_group_summary(df: pd.DataFrame, group_name: str) -> pd.DataFrame:
    total_buy_amount = float(df["총매수금액"].sum())
    closed_buy_amount = float(df["_사고판매수금액"].sum())
    closed_profit = float(df["사고판수익"].sum())
    realized_profit = float(df["실현손익"].sum())
    unrealized_profit = float(df["미실현손익"].sum())
    total_profit = float(df["총손익"].sum())

    summary_row = {column: "" for column in df.columns}
    summary_row["그룹"] = group_name
    summary_row["기간"] = df["기간"].iloc[0]
    summary_row["티커"] = "합계"
    summary_row["종목명"] = f"{group_name} 합계"
    summary_row["상태"] = "합계"
    summary_row["총매수금액"] = round(total_buy_amount, 2)
    summary_row["_사고판매수금액"] = round(closed_buy_amount, 2)
    summary_row["사고판수익"] = round(closed_profit, 2)
    summary_row["사고판수익률(%)"] = round((closed_profit / closed_buy_amount * 100), 2) if closed_buy_amount else 0.0
    summary_row["실현손익"] = round(realized_profit, 2)
    summary_row["미실현손익"] = round(unrealized_profit, 2)
    summary_row["총손익"] = round(total_profit, 2)
    summary_row["수익률(%)"] = round((total_profit / total_buy_amount * 100), 2) if total_buy_amount else 0.0

    return pd.concat([df, pd.DataFrame([summary_row])], ignore_index=True)


def print_group_result(group_name: str, window: BacktestWindow, df: pd.DataFrame) -> None:
    bar = "=" * 140
    print(f"\n{bar}")
    print(f"[{window.title}] {group_name} Type1 백테스트")
    print(bar)

    if df.empty:
        print("  결과 없음")
        return

    def format_number(value):
        if value == "":
            return ""
        number = float(value)
        return int(number) if number.is_integer() else round(number, 2)

    display_df = df.drop(columns=["_사고판매수금액"]).copy()
    for column in ["평가종가", "총매수금액", "사고판수익", "사고판수익률(%)", "실현손익", "미실현손익", "총손익", "수익률(%)"]:
        display_df[column] = display_df[column].map(format_number)

    right_cols = {"평가종가", "보유주식수", "매수횟수", "매도횟수", "총매수금액", "사고판수익", "사고판수익률(%)", "실현손익", "미실현손익", "총손익", "수익률(%)"}
    print_table(display_df, right_cols=right_cols)


def save_window_result(output_csv: str | None, dfs: list[pd.DataFrame]) -> Path | None:
    if not output_csv:
        return None

    frames = [df for df in dfs if not df.empty]
    if not frames:
        return None

    result_df = pd.concat(frames, ignore_index=True).drop(columns=["_사고판매수금액"])
    output_path = Path(output_csv)
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result_df.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path


def main() -> None:
    args = parse_args()
    window = build_window(args.from_date, args.to_date)

    print("Type1 백테스트를 시작합니다...")
    print(f"기준일: {datetime.now().strftime('%Y-%m-%d')}")
    print(f"기간: {window.title}")
    print(f"규칙: -→+ 10주 매수 / +→- 전량 매도 / 미청산은 --to 기준 평가")

    universe = build_universe()
    group_results: list[pd.DataFrame] = []
    for group_name, items in universe:
        df = run_group_backtest(group_name, items, window)
        group_results.append(df)
        print_group_result(group_name, window, df)

    output_path = save_window_result(args.output_csv, group_results)
    if output_path:
        print(f"\n→ CSV 저장: {output_path}")


if __name__ == "__main__":
    main()
