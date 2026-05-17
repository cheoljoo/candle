"""foreign_trading.py
KOSPI200 종목별 외국인/기관 일별 순매수 데이터 수집 (pykrx).

저장 경로:
  data/market/foreign/{ticker}.csv
    컬럼: date, 기관합계, 외국인합계, 개인

운영 방식:
  - 증분 수집: 기존 CSV 마지막 날짜 다음날부터 오늘까지
  - KOSPI200 종목만 대상 (SP500/ETF는 해당 없음)
  - ThreadPoolExecutor로 병렬 수집 (기본 4 workers)

활용:
  - 최근 5일 외국인/기관 순매수 합산 → 매매 강도 지표
  - dashboard group_returns 상세 행에 표시
"""
from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

# 증분 수집 fallback 기간 (CSV 없을 때)
_FALLBACK_DAYS = 400


def _fetch_one_ticker(
    ticker: str,
    start: date,
    end: date,
    save_path: Path,
) -> tuple[str, int, str | None]:
    """단일 종목 외국인/기관 매매 데이터 수집 후 CSV 저장.

    Returns:
        (ticker, rows_added, error_msg_or_None)
    """
    try:
        from pykrx import stock
    except ImportError:
        return ticker, 0, "pykrx 미설치"

    s = start.strftime("%Y%m%d")
    e = end.strftime("%Y%m%d")

    existing = pd.DataFrame()
    if save_path.exists():
        try:
            existing = pd.read_csv(save_path)
        except Exception:
            pass

    try:
        df = stock.get_market_trading_value_by_date(s, e, ticker)
    except Exception as exc:
        return ticker, 0, str(exc)

    if df is None or df.empty:
        return ticker, 0, None

    df = df.reset_index()
    date_col = next((c for c in df.columns if "날짜" in str(c) or c in ("Date", "date")), df.columns[0])
    df = df.rename(columns={date_col: "date"})
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

    # 필요 컬럼만 유지 (명칭이 다를 수 있으므로 유연하게 처리)
    keep_cols = {"date": "date"}
    col_candidates = {
        "기관합계": ["기관합계", "기관_합계", "Institutional"],
        "외국인합계": ["외국인합계", "외국인_합계", "외국인", "Foreign"],
        "개인": ["개인", "Individual"],
    }
    for target, candidates in col_candidates.items():
        found = next((c for c in candidates if c in df.columns), None)
        if found:
            keep_cols[found] = target

    rename_map = {k: v for k, v in keep_cols.items() if k != "date"}
    cols_to_keep = ["date"] + [k for k in rename_map]
    df = df[[c for c in cols_to_keep if c in df.columns]].rename(columns=rename_map)

    combined = pd.concat([existing, df], ignore_index=True) if not existing.empty else df
    combined = (combined
                .drop_duplicates(subset=["date"])
                .sort_values("date")
                .reset_index(drop=True))

    save_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(save_path, index=False)
    return ticker, len(df), None


def run(
    data_dir: Path,
    tickers: list[str],
    end: date | None = None,
    workers: int = max(1, (os.cpu_count() or 4) // 2),
    verbose: bool = True,
) -> dict:
    """KOSPI200 종목별 외국인/기관 매매 데이터 증분 수집.

    Args:
        data_dir: 프로젝트 data/ 디렉터리
        tickers:  수집 대상 ticker 목록 (KOSPI200 종목)
        end:      조회 종료일 (기본=오늘)
        workers:  병렬 worker 수
        verbose:  진행 출력 여부

    Returns:
        {ticker: rows_added} 딕셔너리
    """
    if end is None:
        end = date.today()

    foreign_dir = data_dir / "market" / "foreign"
    foreign_dir.mkdir(parents=True, exist_ok=True)

    def _get_start(ticker: str) -> date:
        p = foreign_dir / f"{ticker}.csv"
        if p.exists():
            try:
                df = pd.read_csv(p)
                if not df.empty:
                    return pd.to_datetime(df["date"].max()).date() + timedelta(days=1)
            except Exception:
                pass
        return end - timedelta(days=_FALLBACK_DAYS)

    results: dict[str, int] = {}
    errors: dict[str, str] = {}
    total = len(tickers)

    def _task(tk: str) -> tuple[str, int, str | None]:
        start = _get_start(tk)
        if start > end:
            return tk, 0, None
        save_path = foreign_dir / f"{tk}.csv"
        return _fetch_one_ticker(tk, start, end, save_path)

    if verbose:
        print(f"[foreign-trading] {total}개 종목 수집 시작 (workers={workers})", flush=True)

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_task, tk): tk for tk in tickers}
        for fut in as_completed(futures):
            tk, n, err = fut.result()
            done += 1
            results[tk] = n
            if err:
                errors[tk] = err
                log.warning("foreign-trading 수집 실패 %s: %s", tk, err)
            if verbose and (done % 20 == 0 or done == total):
                pct = done * 100 // total
                print(f"[foreign-trading] {done}/{total} ({pct}%)", flush=True)

    if verbose:
        added = sum(v for v in results.values() if v > 0)
        print(f"[foreign-trading] 완료 — {added}건 추가, 오류 {len(errors)}개", flush=True)

    return results


def load_recent(
    data_dir: Path,
    ticker: str,
    days: int = 5,
) -> dict | None:
    """단일 종목 최근 N일 외국인/기관 순매수 합산 로드.

    Returns:
        {'기관합계': int, '외국인합계': int, '개인': int, 'rows': int}
        또는 데이터 없으면 None
    """
    p = data_dir / "market" / "foreign" / f"{ticker}.csv"
    if not p.exists():
        return None
    try:
        df = pd.read_csv(p)
        if df.empty:
            return None
        df = df.sort_values("date").tail(days)
        out: dict = {"rows": len(df)}
        for col in ["기관합계", "외국인합계", "개인"]:
            if col in df.columns:
                out[col] = int(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())
        return out
    except Exception as exc:
        log.warning("foreign load 실패 %s: %s", ticker, exc)
        return None


def load_latest_snapshot(
    data_dir: Path,
    tickers: list[str],
    days: int = 5,
) -> dict[str, dict]:
    """여러 종목 최근 N일 외국인/기관 순매수 합산 스냅샷.

    Returns:
        {ticker: {'기관합계': int, '외국인합계': int, '개인': int, 'rows': int}}
    """
    out: dict[str, dict] = {}
    for tk in tickers:
        rec = load_recent(data_dir, tk, days)
        if rec:
            out[tk] = rec
    return out
