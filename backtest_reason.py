"""
backtest_reason.py

backtest_type1.csv 결과를 읽어 수익률 상/하위 종목의 차이를 요약합니다.
각 종목에 대해 기간 주가상승률, 거래 횟수, 미실현 비중, 종료 시점 낙폭 등을 계산해
왜 수익률이 크게/작게 나왔는지 설명 문구를 출력합니다.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import FinanceDataReader as fdr
import pandas as pd

from analyze import STOCKS_DIR, US_STOCKS_DIR, print_table
from backtest_type1 import load_price_frame


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "backtest_type1.csv를 읽어 상위/하위 수익률 종목의 차이를 분석합니다. "
            "기간 주가상승률, 거래횟수, 첫 매수일 거래량 비교, 닫힌 거래 손익, 미실현 비중을 함께 보여줍니다."
        )
    )
    parser.add_argument(
        "--input_csv",
        default="backtest_type1.csv",
        help="분석할 backtest 결과 CSV 경로 (기본값: backtest_type1.csv)",
    )
    parser.add_argument(
        "--top_n",
        type=int,
        default=7,
        help="상위/하위에서 볼 종목 수 (기본값: 7)",
    )
    return parser.parse_args()


def source_path(group_name: str, ticker: str) -> Path:
    if group_name == "KOSPI 200":
        return STOCKS_DIR / f"{ticker}.csv"
    return US_STOCKS_DIR / f"{ticker}.csv"


def compute_period_stats(group_name: str, ticker: str, start_date: str, price_date: str) -> dict:
    df = load_price_frame(source_path(group_name, ticker))
    if df is None:
        return {
            "기간주가상승률(%)": 0.0,
            "최대상승률(%)": 0.0,
            "종료낙폭(%)": 0.0,
        }

    period_df = df.loc[(df.index >= pd.Timestamp(start_date)) & (df.index <= pd.Timestamp(price_date))]
    if period_df.empty:
        return {
            "기간주가상승률(%)": 0.0,
            "최대상승률(%)": 0.0,
            "종료낙폭(%)": 0.0,
        }

    first_close = float(period_df["Close"].iloc[0])
    end_close = float(period_df["Close"].iloc[-1])
    peak_close = float(period_df["Close"].max())
    price_return = ((end_close - first_close) / first_close * 100) if first_close else 0.0
    max_runup = ((peak_close - first_close) / first_close * 100) if first_close else 0.0
    end_drawdown = ((end_close - peak_close) / peak_close * 100) if peak_close else 0.0
    return {
        "기간주가상승률(%)": round(price_return, 2),
        "최대상승률(%)": round(max_runup, 2),
        "종료낙폭(%)": round(end_drawdown, 2),
    }


def find_first_buy_stats(group_name: str, ticker: str, start_date: str, price_date: str) -> dict:
    df = load_price_frame(source_path(group_name, ticker))
    if df is None:
        return empty_first_buy_stats()

    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(price_date)
    period_df = df.loc[(df.index >= start_ts) & (df.index <= end_ts)].copy()
    previous_row = df.loc[df.index < start_ts].tail(1)
    if period_df.empty:
        return empty_first_buy_stats()

    signal_df = pd.concat([previous_row, period_df]) if not previous_row.empty else period_df
    signal_df = signal_df.dropna(subset=["MA10M"])
    if len(signal_df) < 2:
        return empty_first_buy_stats()

    is_positive = signal_df["Close"] > signal_df["MA10M"]
    for i in range(1, len(signal_df)):
        trade_date = signal_df.index[i]
        if trade_date < start_ts or trade_date > end_ts:
            continue

        prev_positive = bool(is_positive.iloc[i - 1])
        curr_positive = bool(is_positive.iloc[i])
        if not prev_positive and curr_positive:
            close_price = float(signal_df["Close"].iloc[i])
            ma10_price = float(signal_df["MA10M"].iloc[i])
            divergence = ((close_price - ma10_price) / ma10_price * 100) if ma10_price else 0.0
            delay_days = (trade_date - start_ts).days
            return {
                "첫매수일": trade_date.strftime("%Y-%m-%d"),
                "첫매수지연일수": delay_days,
                "첫매수이격률(%)": round(divergence, 2),
            }

    return empty_first_buy_stats()


def empty_first_buy_stats() -> dict:
    return {
        "첫매수일": "-",
        "첫매수지연일수": -1,
        "첫매수이격률(%)": 0.0,
    }


def fetch_volume_stats(group_name: str, ticker: str, buy_date: pd.Timestamp) -> dict:
    start = (buy_date - pd.Timedelta(days=45)).strftime("%Y-%m-%d")
    end = (buy_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    try:
        raw_df = fdr.DataReader(ticker, start=start, end=end)
    except Exception:
        return {
            "첫매수거래량": 0.0,
            "직전20일평균거래량": 0.0,
            "거래량배수": 0.0,
        }

    if raw_df is None or raw_df.empty or "Volume" not in raw_df.columns:
        return {
            "첫매수거래량": 0.0,
            "직전20일평균거래량": 0.0,
            "거래량배수": 0.0,
        }

    raw_df = raw_df.sort_index()
    buy_ts = pd.Timestamp(buy_date)
    if buy_ts not in raw_df.index:
        buy_slice = raw_df.loc[raw_df.index <= buy_ts]
        if buy_slice.empty:
            return {
                "첫매수거래량": 0.0,
                "직전20일평균거래량": 0.0,
                "거래량배수": 0.0,
            }
        buy_ts = buy_slice.index[-1]

    buy_volume = float(raw_df.loc[buy_ts, "Volume"])
    prev_volume = raw_df.loc[raw_df.index < buy_ts, "Volume"].tail(20)
    avg_volume = float(prev_volume.mean()) if not prev_volume.empty else 0.0
    volume_multiple = (buy_volume / avg_volume) if avg_volume else 0.0
    return {
        "첫매수거래량": round(buy_volume, 2),
        "직전20일평균거래량": round(avg_volume, 2),
        "거래량배수": round(volume_multiple, 2),
    }


def enrich_with_volume(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    volume_rows = []
    for row in df.to_dict("records"):
        if row["첫매수일"] == "-":
            volume_rows.append({
                "첫매수거래량": 0.0,
                "직전20일평균거래량": 0.0,
                "거래량배수": 0.0,
            })
            continue
        volume_rows.append(
            fetch_volume_stats(row["그룹"], row["티커"], pd.Timestamp(row["첫매수일"]))
        )

    return pd.concat([df.reset_index(drop=True), pd.DataFrame(volume_rows)], axis=1)


def build_reason(row: pd.Series) -> str:
    reasons: list[str] = []
    volume_multiple = row.get("거래량배수", 0.0)

    if row["보유주식수"] > 0 and row["미실현손익"] > max(abs(row["사고판수익"]) * 2, 0):
        reasons.append("최근 보유분 평가이익이 성과 대부분")
    if row["매수횟수"] == 1 and row["매도횟수"] == 0:
        reasons.append("첫 진입 후 장기 보유")
    if volume_multiple >= 2:
        reasons.append("첫 매수일 거래량 급증 동반")
    if row["매도횟수"] >= 3 and row["사고판수익률(%)"] <= 0:
        reasons.append("MA10M 근처 왕복매매 손실 누적")
    if row["보유주식수"] == 0 and row["미실현손익"] == 0:
        reasons.append("닫힌 거래 결과만 최종 성과에 반영")
    if row["기간주가상승률(%)"] >= 80:
        reasons.append("기간 자체의 강한 주가 상승")
    if row["종료낙폭(%)"] <= -20:
        reasons.append("종료 시점이 고점 대비 큰 조정 구간")
    if row["수익률(%)"] < 0 and row["사고판수익률(%)"] < 0 and row["보유주식수"] == 0:
        reasons.append("모든 거래가 닫혔고 손실이 확정됨")

    if not reasons:
        if row["보유주식수"] > 0:
            reasons.append("닫힌 거래와 보유 평가손익이 혼합된 결과")
        else:
            reasons.append("닫힌 거래 누적 손익이 성과 결정")

    return " / ".join(reasons[:3])


def summarize_slice(df: pd.DataFrame, label: str) -> dict:
    total_buy = float(df["총매수금액"].sum())
    closed_buy = float(df["_사고판매수금액"].sum())
    total_profit = float(df["총손익"].sum())
    closed_profit = float(df["사고판수익"].sum())

    return {
        "구간": label,
        "종목수": len(df),
        "평균수익률(%)": round(float(df["수익률(%)"].mean()), 2),
        "평균기간주가상승률(%)": round(float(df["기간주가상승률(%)"].mean()), 2),
        "평균매수횟수": round(float(df["매수횟수"].mean()), 2),
        "평균매도횟수": round(float(df["매도횟수"].mean()), 2),
        "보유종목비중(%)": round(float((df["보유주식수"] > 0).mean() * 100), 2),
        "평균첫매수지연일수": round(float(df["첫매수지연일수"].replace(-1, pd.NA).dropna().mean()), 2) if not df["첫매수지연일수"].replace(-1, pd.NA).dropna().empty else 0.0,
        "평균거래량배수": round(float(df["거래량배수"].mean()), 2) if "거래량배수" in df.columns else 0.0,
        "합계사고판수익률(%)": round((closed_profit / closed_buy * 100), 2) if closed_buy else 0.0,
        "합계전체수익률(%)": round((total_profit / total_buy * 100), 2) if total_buy else 0.0,
    }


def analyze_group(df: pd.DataFrame, group_name: str, top_n: int) -> None:
    group_df = df[df["그룹"] == group_name].copy()
    if group_df.empty:
        return

    group_df = group_df.sort_values(by="수익률(%)", ascending=False).reset_index(drop=True)
    top_df = enrich_with_volume(group_df.head(top_n).copy())
    bottom_df = enrich_with_volume(group_df.tail(top_n).copy())

    diff_df = pd.DataFrame([
        summarize_slice(top_df, "상위"),
        summarize_slice(bottom_df, "하위"),
    ])

    display_cols = [
        "티커", "종목명", "수익률(%)", "사고판수익률(%)", "기간주가상승률(%)",
        "최대상승률(%)", "종료낙폭(%)", "첫매수일", "첫매수지연일수", "첫매수이격률(%)",
        "거래량배수", "매수횟수", "매도횟수", "보유주식수", "사고판수익", "미실현손익", "총손익", "원인",
    ]
    top_display = top_df[display_cols]
    bottom_display = bottom_df.sort_values(by="수익률(%)", ascending=True)[display_cols]

    print("\n" + "=" * 160)
    print(f"[{group_name}] 상/하위 수익률 차이 요약")
    print("=" * 160)
    print_table(diff_df, right_cols=set(diff_df.columns) - {"구간"})

    print(f"\n[{group_name}] 상위 {len(top_display)} 종목")
    print_table(top_display, right_cols={
        "수익률(%)", "사고판수익률(%)", "기간주가상승률(%)", "최대상승률(%)", "종료낙폭(%)",
        "첫매수지연일수", "첫매수이격률(%)", "거래량배수", "매수횟수", "매도횟수", "보유주식수",
        "사고판수익", "미실현손익", "총손익",
    })

    print(f"\n[{group_name}] 하위 {len(bottom_display)} 종목")
    print_table(bottom_display, right_cols={
        "수익률(%)", "사고판수익률(%)", "기간주가상승률(%)", "최대상승률(%)", "종료낙폭(%)",
        "첫매수지연일수", "첫매수이격률(%)", "거래량배수", "매수횟수", "매도횟수", "보유주식수",
        "사고판수익", "미실현손익", "총손익",
    })


def main() -> None:
    args = parse_args()
    path = Path(args.input_csv)
    if not path.exists():
        raise FileNotFoundError(f"{path} 없음")

    df = pd.read_csv(path)
    df = df[df["티커"] != "합계"].copy()
    if df.empty:
        raise ValueError("분석할 종목 데이터가 없습니다.")

    numeric_cols = [
        "평가종가", "보유주식수", "매수횟수", "매도횟수", "총매수금액",
        "사고판수익", "사고판수익률(%)", "실현손익", "미실현손익", "총손익", "수익률(%)",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    df["_사고판매수금액"] = 0.0
    closed_mask = df["매도횟수"] > 0
    df.loc[closed_mask, "_사고판매수금액"] = (
        df.loc[closed_mask, "사고판수익"] / (df.loc[closed_mask, "사고판수익률(%)"] / 100)
    ).replace([pd.NA, pd.NaT, float("inf"), float("-inf")], 0.0)

    starts = df["기간"].str.split(" ~ ").str[0]
    stats_rows = []
    for row, start_date in zip(df.to_dict("records"), starts):
        price_stats = compute_period_stats(row["그룹"], row["티커"], start_date, row["평가가격일"])
        first_buy_stats = find_first_buy_stats(row["그룹"], row["티커"], start_date, row["평가가격일"])
        stats_rows.append({**price_stats, **first_buy_stats})
    stats_df = pd.DataFrame(stats_rows)
    df = pd.concat([df.reset_index(drop=True), stats_df], axis=1)
    df["원인"] = df.apply(build_reason, axis=1)

    for group_name in ["KOSPI 200", "S&P500", "ETF"]:
        analyze_group(df, group_name, args.top_n)


if __name__ == "__main__":
    main()
