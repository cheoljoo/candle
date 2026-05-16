"""market_signals.py
KOSPI 시장 신호 데이터 수집:
  1. 프로그램 매매 (차익/비차익 순매도) — KRX MDCSTAT02601
  2. 투자자별 매매 동향 (금융투자·외국인·기관합계 등) — pykrx

저장 경로:
  data/market/program_trading.csv
  data/market/investor_trading.csv

시그널 임계값 결정 방식:
  - 고정 절대값 대신 역사적 분포의 하위 퍼센타일 사용
  - 기본: 하위 10% (지난 ~1년 거래일 중 가장 극단적인 순매도 상위 10%)
  - 금융투자 연속 순매도: 하위 20% 기준 N일 연속

보는 법:
  - 비차익 순매도가 역사적 하위 10% 수준 → ETF/인덱스 기계적 매도 신호
  - 금융투자 3일 연속 하위 20% → ETF 자금 이탈 신호
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

# 퍼센타일 기반 임계값 (고정값 대신 역사적 분포 사용)
PROGRAM_SELL_PERCENTILE = 10   # 하위 10% → 순매도 상위 10%일 때 경보
FINV_SELL_PERCENTILE    = 20   # 하위 20% 기준
FINV_CONSEC_DAYS        = 3    # 연속 일수

# 퍼센타일 계산에 사용할 lookback 거래일 수 (약 1년)
LOOKBACK_TRADING_DAYS = 250

# 역사적 데이터 부족 시 fallback 절대값 (원)
PROGRAM_SELL_FALLBACK = -300_000_000_000   # -3000억
FINV_SELL_FALLBACK    = -300_000_000_000   # -3000억


# ─────────────────────────────────────────────────────────────────────────────
# 프로그램 매매
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_program_trading_one_day(trd_dd: str, mkt_id: str = "STK") -> dict | None:
    """KRX MDCSTAT02601로 특정 거래일의 프로그램 차익/비차익 데이터 수집.

    Args:
        trd_dd:  조회 일자 (YYYYMMDD)
        mkt_id:  STK=KOSPI, KSQ=KOSDAQ

    Returns:
        {'date': str, '차익_순매수': int, '비차익_순매수': int, '전체_순매수': int}
        또는 None (데이터 없음)
    """
    try:
        from pykrx.website.krx.krxio import KrxWebIo

        class _ProgramTrading(KrxWebIo):
            @property
            def bld(self):
                return "dbms/MDC/STAT/standard/MDCSTAT02601"

            def fetch(self, strt_dd: str, end_dd: str, mkt_id: str) -> pd.DataFrame:
                result = self.read(strtDd=strt_dd, endDd=end_dd, mktId=mkt_id)
                if not result or not result.get("output"):
                    return pd.DataFrame()
                return pd.DataFrame(result["output"])

        df = _ProgramTrading().fetch(trd_dd, trd_dd, mkt_id)
        if df.empty:
            return None

        def _parse_val(row_filter: str, col: str) -> int:
            rows = df[df["ITM_TP_NM"] == row_filter]
            if rows.empty:
                return 0
            raw = rows.iloc[0][col].replace(",", "")
            return int(raw)

        return {
            "date": f"{trd_dd[:4]}-{trd_dd[4:6]}-{trd_dd[6:]}",
            "차익_순매수":   _parse_val("차익",  "NETBID_TRDVAL"),
            "비차익_순매수": _parse_val("비차익", "NETBID_TRDVAL"),
            "전체_순매수":   _parse_val("전체",   "NETBID_TRDVAL"),
        }
    except Exception as exc:
        log.warning("프로그램 매매 수집 실패 %s: %s", trd_dd, exc)
        return None


def _get_trading_days(start: date, end: date) -> list[date]:
    """pykrx KOSPI 인덱스 OHLCV에서 실제 거래일 목록 추출 (달력일 루프 불필요)."""
    try:
        from pykrx import stock
        s = start.strftime("%Y%m%d")
        e = end.strftime("%Y%m%d")
        df = stock.get_index_ohlcv(s, e, "1001")  # 1001 = KOSPI
        if df is None or df.empty:
            return []
        return [d.date() for d in df.index]
    except Exception as exc:
        log.warning("거래일 조회 실패, 달력일 fallback: %s", exc)
        days = []
        cur = start
        while cur <= end:
            if cur.weekday() < 5:  # 월~금
                days.append(cur)
            cur += timedelta(days=1)
        return days


def fetch_program_trading(
    start: date,
    end: date,
    save_path: Path | None = None,
    mkt_id: str = "STK",
) -> pd.DataFrame:
    """start~end 기간 프로그램 매매 일별 데이터 수집 (거래일만 루프).

    기존 save_path CSV가 있으면 누락 날짜만 보완(증분).

    Returns:
        DataFrame: date, 차익_순매수, 비차익_순매수, 전체_순매수
    """
    existing = pd.DataFrame()
    existing_dates: set[str] = set()
    if save_path and save_path.exists():
        existing = pd.read_csv(save_path)
        existing_dates = set(existing["date"].astype(str))

    trading_days = _get_trading_days(start, end)
    records: list[dict] = []
    for d in trading_days:
        d_iso = d.strftime("%Y-%m-%d")
        if d_iso in existing_dates:
            continue
        rec = _fetch_program_trading_one_day(d.strftime("%Y%m%d"), mkt_id)
        if rec:
            records.append(rec)

    if not records and existing.empty:
        return pd.DataFrame(columns=["date", "차익_순매수", "비차익_순매수", "전체_순매수"])

    new_df = pd.DataFrame(records) if records else pd.DataFrame()
    combined = pd.concat([existing, new_df], ignore_index=True) if not existing.empty else new_df
    combined = combined.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)

    if save_path:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        combined.to_csv(save_path, index=False)
        log.info("프로그램 매매 저장: %s (%d행)", save_path, len(combined))

    return combined


# ─────────────────────────────────────────────────────────────────────────────
# 투자자별 매매 동향
# ─────────────────────────────────────────────────────────────────────────────

def fetch_investor_trading(
    start: date,
    end: date,
    save_path: Path | None = None,
    market: str = "KOSPI",
) -> pd.DataFrame:
    """pykrx로 투자자별(금융투자·외국인·기관합계 등) 일별 순매수 수집.

    Args:
        market: "KOSPI" | "KOSDAQ"

    Returns:
        DataFrame: date + 금융투자, 보험, 투신, 사모, 은행, 기타금융, 연기금, 기타법인, 개인, 외국인, 기타외국인
    """
    try:
        from pykrx import stock
    except ImportError:
        log.error("pykrx 미설치")
        return pd.DataFrame()

    s = start.strftime("%Y%m%d")
    e = end.strftime("%Y%m%d")

    existing = pd.DataFrame()
    if save_path and save_path.exists():
        existing = pd.read_csv(save_path)

    try:
        df = stock.get_market_trading_value_by_date(s, e, market, detail=True)
    except Exception as exc:
        log.warning("투자자별 매매 수집 실패: %s", exc)
        return existing

    if df is None or df.empty:
        return existing

    df = df.reset_index().rename(columns={"날짜": "date"})
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

    combined = pd.concat([existing, df], ignore_index=True) if not existing.empty else df
    combined = combined.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)

    if save_path:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        combined.to_csv(save_path, index=False)
        log.info("투자자별 매매 저장: %s (%d행)", save_path, len(combined))

    return combined


# ─────────────────────────────────────────────────────────────────────────────
# KOSPI 지수
# ─────────────────────────────────────────────────────────────────────────────

def fetch_kospi_index(
    start: date,
    end: date,
    save_path: "Path | None" = None,
) -> pd.DataFrame:
    """pykrx로 KOSPI 지수 일별 종가 수집 (증분).

    Returns:
        DataFrame: date, close
    """
    try:
        from pykrx import stock
    except ImportError:
        log.error("pykrx 미설치")
        return pd.DataFrame()

    existing = pd.DataFrame()
    if save_path and save_path.exists():
        existing = pd.read_csv(save_path)

    s = start.strftime("%Y%m%d")
    e = end.strftime("%Y%m%d")
    try:
        raw = stock.get_index_ohlcv(s, e, "1001")  # 1001 = KOSPI
    except Exception as exc:
        log.warning("KOSPI 지수 수집 실패: %s", exc)
        return existing

    if raw is None or raw.empty:
        return existing

    df = raw.reset_index()
    # pykrx 버전에 따라 컨럼명 상이
    date_col  = next((c for c in df.columns if "날짜" in str(c) or c == "Date"), df.columns[0])
    close_col = next((c for c in df.columns if "종가" in str(c) or c == "Close"), "종가")
    df = df.rename(columns={date_col: "date", close_col: "close"})
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df = df[["date", "close"]].copy()
    df["close"] = pd.to_numeric(df["close"], errors="coerce")

    combined = pd.concat([existing, df], ignore_index=True) if not existing.empty else df
    combined = combined.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)

    if save_path:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        combined.to_csv(save_path, index=False)
        log.info("KOSPI 지수 저장: %s (%d행)", save_path, len(combined))

    return combined

def _calc_correlation(s1: pd.Series, s2: pd.Series) -> "float | None":
    """Pearson 상관계수 반환 (데이터 부족 시 None)."""
    df = pd.DataFrame({"a": s1, "b": s2}).dropna()
    if len(df) < 10:
        return None
    return round(float(df["a"].corr(df["b"])), 3)


def _percentile_threshold(series: pd.Series, pct: int, fallback: int) -> tuple[float, str]:
    """역사적 분포에서 하위 pct% 값을 임계값으로 반환.

    Returns:
        (threshold, method): method는 'percentile' 또는 'fallback'
    """
    vals = series.dropna()
    if len(vals) < 20:
        return float(fallback), "fallback"
    return float(vals.quantile(pct / 100)), "percentile"


def check_signals(
    program_df: pd.DataFrame,
    investor_df: pd.DataFrame,
    kospi_df: "pd.DataFrame | None" = None,
    as_of: "date | None" = None,
    consec_days: int = FINV_CONSEC_DAYS,
    program_pct: int = PROGRAM_SELL_PERCENTILE,
    finv_pct: int = FINV_SELL_PERCENTILE,
    lookback: int = LOOKBACK_TRADING_DAYS,
) -> dict:
    """역사적 퍼센타일 기반 ETF 매도 시그널 판단.

    시그널 논리:
      - 프로그램 비차익: 최근 N거래일(lookback) 분포에서 하위 program_pct% 이하
      - 금융투자:        최근 N거래일 분포에서 하위 finv_pct% 이하가 consec_days 연속

    Returns:
        {
          'program_signal': bool,
          'program_value': int,
          'program_threshold': float,  # 퍼센타일 임계값
          'program_pct_rank': float,   # 오늘값의 역사적 백분위 (낮을수록 극단적 매도)
          'finv_signal': bool,
          'finv_consec': int,
          'finv_value': int,
          'finv_threshold': float,
          'signals': list[str],
          'stats': dict,               # 역사적 통계 요약
        }
    """
    result: dict = {
        "program_signal": False, "program_value": 0,
        "program_threshold": 0.0, "program_pct_rank": 50.0,
        "program_max_sell": 0,   # 역사적 최대 순매도 (가장 음수인 값)
        "program_max_ratio": 0.0,  # 오늘값 / 역사적최대 × 100
        "finv_signal": False, "finv_consec": 0, "finv_value": 0,
        "finv_threshold": 0.0,
        "finv_max_sell": 0,
        "finv_max_ratio": 0.0,
        "prog_kospi_corr": None,   # Pearson r (프로그램비차익 vs KOSPI종가)
        "finv_kospi_corr": None,   # Pearson r (금융투자 vs KOSPI종가)
        "kospi_data": {},          # {date_str: close_float}
        "signals": [], "stats": {},
    }
    today_str = (as_of or date.today()).strftime("%Y-%m-%d")

    # ── 프로그램 비차익 ──────────────────────────────────────────────────
    if not program_df.empty and "비차익_순매수" in program_df.columns:
        hist = program_df[program_df["date"] <= today_str].tail(lookback)
        threshold, method = _percentile_threshold(
            hist["비차익_순매수"], program_pct, PROGRAM_SELL_FALLBACK
        )
        latest = hist.tail(1)
        if not latest.empty:
            val = int(latest.iloc[0]["비차익_순매수"])
            result["program_value"] = val
            result["program_threshold"] = threshold

            # 역사적 백분위 계산 (오늘값이 전체 중 몇 %에 해당하는지)
            all_vals = hist["비차익_순매수"].dropna()
            pct_rank = float((all_vals < val).sum() / len(all_vals) * 100) if len(all_vals) > 0 else 50.0
            result["program_pct_rank"] = pct_rank

            max_sell = int(all_vals.min()) if len(all_vals) > 0 else 0
            max_ratio = round(val / max_sell * 100, 1) if max_sell != 0 else 0.0
            result["program_max_sell"] = max_sell
            result["program_max_ratio"] = max_ratio

            result["stats"]["program"] = {
                "method": method,
                "lookback_days": len(hist),
                "min_억": round(all_vals.min() / 1e8, 0) if len(all_vals) > 0 else None,
                "max_억": round(all_vals.max() / 1e8, 0) if len(all_vals) > 0 else None,
                "mean_억": round(all_vals.mean() / 1e8, 0) if len(all_vals) > 0 else None,
                f"p{program_pct}_threshold_억": round(threshold / 1e8, 0),
                "today_pct_rank": round(pct_rank, 1),
            }

            if val <= threshold:
                result["program_signal"] = True
                result["signals"].append(
                    f"[⚠ 프로그램 비차익 순매도] {latest.iloc[0]['date']}: "
                    f"{val/1e8:,.0f}억원 "
                    f"(역사적 하위 {pct_rank:.1f}% — 기준: 하위 {program_pct}%={threshold/1e8:,.0f}억)"
                )

    # ── 금융투자 연속 순매도 ─────────────────────────────────────────────
    if not investor_df.empty and "금융투자" in investor_df.columns:
        hist_inv = investor_df[investor_df["date"] <= today_str].tail(lookback)
        threshold_inv, method_inv = _percentile_threshold(
            hist_inv["금융투자"], finv_pct, FINV_SELL_FALLBACK
        )
        result["finv_threshold"] = threshold_inv

        recent = hist_inv.sort_values("date", ascending=False)
        consec = 0
        for _, row in recent.iterrows():
            if int(row["금융투자"]) <= threshold_inv:
                consec += 1
            else:
                break
        finv_val = int(recent.iloc[0]["금융투자"]) if not recent.empty else 0
        result["finv_value"] = finv_val
        result["finv_consec"] = consec

        all_finv = hist_inv["금융투자"].dropna()
        finv_max_sell = int(all_finv.min()) if len(all_finv) > 0 else 0
        finv_max_ratio = round(finv_val / finv_max_sell * 100, 1) if finv_max_sell != 0 else 0.0
        result["finv_max_sell"] = finv_max_sell
        result["finv_max_ratio"] = finv_max_ratio

        result["stats"]["finv"] = {
            "method": method_inv,
            "lookback_days": len(hist_inv),
            f"p{finv_pct}_threshold_억": round(threshold_inv / 1e8, 0),
            "consecutive_sell_days": consec,
        }

        if consec >= consec_days:
            result["finv_signal"] = True
            result["signals"].append(
                f"[⚠ 금융투자 {consec}일 연속 순매도] 최근일: {finv_val/1e8:,.0f}억원 "
                f"(기준: 하위 {finv_pct}%={threshold_inv/1e8:,.0f}억 × {consec_days}일 연속)"
            )

    # ── KOSPI 상관관계 ───────────────────────────────────────────────────
    if kospi_df is not None and not kospi_df.empty and "close" in kospi_df.columns:
        k_lookup = {str(d): float(c) for d, c in zip(kospi_df["date"], kospi_df["close"])}
        result["kospi_data"] = k_lookup

        k_series = kospi_df.set_index("date")["close"].astype(float)

        if not program_df.empty and "비차익_순매수" in program_df.columns:
            ph = (program_df[program_df["date"] <= today_str]
                  .tail(lookback).set_index("date")["비차익_순매수"].astype(float))
            result["prog_kospi_corr"] = _calc_correlation(ph, k_series.reindex(ph.index))

        if not investor_df.empty and "금융투자" in investor_df.columns:
            ih = (investor_df[investor_df["date"] <= today_str]
                  .tail(lookback).set_index("date")["금융투자"].astype(float))
            result["finv_kospi_corr"] = _calc_correlation(ih, k_series.reindex(ih.index))

    return result


# ─────────────────────────────────────────────────────────────────────────────
# 편의 함수: 한 번에 수집 + 판단
# ─────────────────────────────────────────────────────────────────────────────

def run(
    data_dir: Path,
    end: date | None = None,
    verbose: bool = True,
) -> dict:
    """프로그램/투자자 매매 데이터 수집 및 시그널 판단 진입점.

    증분(incremental) 방식으로 동작:
    - 기존 CSV가 있으면 마지막 날짜 다음날부터 오늘까지 누락분만 수집
    - CSV가 없으면 1년(365일) 전부터 전체 수집
    - --days 파라미터 없음: 항상 최신 데이터만 추가

    Args:
        data_dir: 프로젝트 data/ 디렉터리
        end:      조회 종료일 (기본=오늘)
        verbose:  True면 시그널 출력

    Returns:
        check_signals() 결과 dict
    """
    if end is None:
        end = date.today()

    market_dir = data_dir / "market"
    prog_path = market_dir / "program_trading.csv"
    inv_path  = market_dir / "investor_trading.csv"

    # 증분 fetch: 기존 마지막 날짜 이후부터만 수집
    _FALLBACK_DAYS = 400  # CSV 없을 때 초기 수집 기간 (~1년 + buffer)

    prog_existing = pd.read_csv(prog_path) if prog_path.exists() else pd.DataFrame()
    if not prog_existing.empty:
        prog_start = (pd.to_datetime(prog_existing["date"].max()).date()
                      + timedelta(days=1))
    else:
        prog_start = end - timedelta(days=_FALLBACK_DAYS)

    inv_existing = pd.read_csv(inv_path) if inv_path.exists() else pd.DataFrame()
    if not inv_existing.empty:
        inv_start = (pd.to_datetime(inv_existing["date"].max()).date()
                     + timedelta(days=1))
    else:
        inv_start = end - timedelta(days=_FALLBACK_DAYS)

    prog_df = fetch_program_trading(prog_start, end, save_path=prog_path)
    inv_df  = fetch_investor_trading(inv_start, end, save_path=inv_path)

    # KOSPI 지수 증분 fetch
    kospi_path = market_dir / "kospi_index.csv"
    kospi_existing = pd.read_csv(kospi_path) if kospi_path.exists() else pd.DataFrame()
    if not kospi_existing.empty:
        kospi_start = (pd.to_datetime(kospi_existing["date"].max()).date()
                       + timedelta(days=1))
    else:
        kospi_start = end - timedelta(days=_FALLBACK_DAYS)
    kospi_df = fetch_kospi_index(kospi_start, end, save_path=kospi_path)

    signals = check_signals(prog_df, inv_df, kospi_df=kospi_df, as_of=end)

    if verbose:
        print(f"\n=== 시장 시그널 ({end}) ===")
        _億 = lambda v: f"{v/1e8:+,.0f}억원"

        # 역사적 임계값 정보 출력
        prog_stats = signals.get("stats", {}).get("program", {})
        finv_stats = signals.get("stats", {}).get("finv", {})
        if prog_stats:
            method = prog_stats.get("method", "?")
            lookback = prog_stats.get("lookback_days", "?")
            pN = [k for k in prog_stats if "threshold" in k]
            thr_key = pN[0] if pN else None
            thr_val = prog_stats.get(thr_key, "?") if thr_key else "?"
            print(f"\n[임계값 기준] 프로그램비차익={thr_key}={thr_val}억 "
                  f"(lookback={lookback}거래일, method={method})")

        if not prog_df.empty and "비차익_순매수" in prog_df.columns:
            last5 = prog_df.tail(5)
            thr = signals.get("program_threshold", 0)
            print(f"\n[프로그램 비차익 순매수 최근 5일] (경보기준: {thr/1e8:,.0f}억 이하)")
            for _, r in last5.iterrows():
                val = int(r["비차익_순매수"])
                flag = f" ★매도급증(하위{signals.get('program_pct_rank',50):.0f}%)" if val <= thr and _ == last5.index[-1] else (" ★매도급증" if val <= thr else "")
                print(f"  {r['date']}: {_億(val)}{flag}")

        if not inv_df.empty and "금융투자" in inv_df.columns:
            last5i = inv_df.tail(5)
            thr_i = signals.get("finv_threshold", 0)
            print(f"\n[금융투자 순매수 최근 5일] (경보기준: {thr_i/1e8:,.0f}억 이하)")
            for _, r in last5i.iterrows():
                val_i = int(r["금융투자"])
                flag_i = " ★매도급증" if val_i <= thr_i else ""
                print(f"  {r['date']}: {_億(val_i)}{flag_i}")

        if signals["signals"]:
            print("\n[활성 시그널]")
            for msg in signals["signals"]:
                print(" ", msg)
        else:
            print("\n[시그널 없음] 현재 기준 ETF 기계적 매도 신호 미감지")

        # KOSPI 상관관계 출력
        prog_r = signals.get("prog_kospi_corr")
        finv_r = signals.get("finv_kospi_corr")
        if prog_r is not None or finv_r is not None:
            print(f"\n[KOSPI 상관관계 (Pearson r, lookback={LOOKBACK_TRADING_DAYS}거래일)]")
            if prog_r is not None:
                print(f"  프로그램비차익 vs KOSPI: r={prog_r:+.3f}")
            if finv_r is not None:
                print(f"  금융투자     vs KOSPI: r={finv_r:+.3f}")

        # 역사적 통계 요약
        if prog_stats:
            print(f"\n[역사적 분포 요약 (프로그램비차익, {prog_stats.get('lookback_days')}거래일)]")
            print(f"  최대순매도: {prog_stats.get('min_억'):,.0f}억 | "
                  f"평균: {prog_stats.get('mean_억'):,.0f}억 | "
                  f"최대순매수: {prog_stats.get('max_억'):,.0f}억")
            print(f"  오늘 순위: 하위 {prog_stats.get('today_pct_rank')}% "
                  f"(낮을수록 극단적 순매도)")

    return signals
