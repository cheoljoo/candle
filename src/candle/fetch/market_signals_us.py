"""market_signals_us.py
미국 시장 신호 데이터 수집 (yfinance):
  1. VIX (^VIX) — CBOE 변동성 지수
  2. 미국채 수익률 — 10년(^TNX), 3개월(^IRX)
  3. 수익률 곡선 스프레드 (10Y - 3M): 역전 여부

저장 경로:
  data/market/us_vix.csv         — date, close
  data/market/us_yields.csv      — date, y10, y3m, spread

시그널 임계값:
  - VIX: 역사적 상위 20% 이상 → 공포 시장 경보
  - 수익률 역전 (spread < 0): 경기침체 선행 지표
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

# 퍼센타일 기반 임계값
VIX_FEAR_PERCENTILE    = 80   # 상위 20% (VIX 높을수록 공포)
LOOKBACK_TRADING_DAYS  = 250  # 약 1년


def _fetch_yfinance_series(symbol: str, start: date, end: date,
                           col: str = "Close") -> pd.DataFrame:
    """yfinance로 단일 심볼의 일별 Close 시계열 수집."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        df = ticker.history(
            start=start.strftime("%Y-%m-%d"),
            end=(end + timedelta(days=1)).strftime("%Y-%m-%d"),
        )
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.reset_index()
        date_col = next((c for c in df.columns if "Date" in str(c) or "date" in str(c)), df.columns[0])
        df = df.rename(columns={date_col: "date", col: "close"})
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        df = df[["date", "close"]].copy()
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        return df.dropna(subset=["close"]).reset_index(drop=True)
    except Exception as exc:
        log.warning("yfinance fetch 실패 %s: %s", symbol, exc)
        return pd.DataFrame()


def _incremental_fetch(symbol: str, save_path: Path,
                       end: date, fallback_days: int = 400) -> pd.DataFrame:
    """기존 CSV 마지막 날짜 이후부터 증분 fetch + merge + save."""
    existing = pd.DataFrame()
    if save_path.exists():
        try:
            existing = pd.read_csv(save_path)
        except Exception:
            pass

    if not existing.empty:
        start = pd.to_datetime(existing["date"].max()).date() + timedelta(days=1)
    else:
        start = end - timedelta(days=fallback_days)

    if start > end:
        return existing

    new_df = _fetch_yfinance_series(symbol, start, end)
    if new_df.empty and existing.empty:
        return pd.DataFrame()

    combined = pd.concat([existing, new_df], ignore_index=True) if not existing.empty else new_df
    combined = (combined
                .drop_duplicates(subset=["date"])
                .sort_values("date")
                .reset_index(drop=True))

    save_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(save_path, index=False)
    log.info("%s 저장: %s (%d행)", symbol, save_path, len(combined))
    return combined


def fetch_vix(data_dir: Path, end: date | None = None) -> pd.DataFrame:
    """VIX 지수 일별 종가 증분 수집.

    Returns:
        DataFrame: date, close (VIX 포인트)
    """
    if end is None:
        end = date.today()
    return _incremental_fetch("^VIX", data_dir / "market" / "us_vix.csv", end)


def fetch_us_yields(data_dir: Path, end: date | None = None) -> pd.DataFrame:
    """미국채 10년(^TNX), 3개월(^IRX) 수익률 증분 수집 + 스프레드 계산.

    Returns:
        DataFrame: date, y10, y3m, spread (10Y - 3M, %)
    """
    if end is None:
        end = date.today()
    market_dir = data_dir / "market"
    yields_path = market_dir / "us_yields.csv"

    existing = pd.DataFrame()
    if yields_path.exists():
        try:
            existing = pd.read_csv(yields_path)
        except Exception:
            pass

    if not existing.empty:
        start = pd.to_datetime(existing["date"].max()).date() + timedelta(days=1)
    else:
        start = end - timedelta(days=400)

    if start > end:
        return existing

    df10 = _fetch_yfinance_series("^TNX", start, end).rename(columns={"close": "y10"})
    df3m = _fetch_yfinance_series("^IRX", start, end).rename(columns={"close": "y3m"})

    if df10.empty and df3m.empty:
        return existing

    # merge on date (outer join)
    if df10.empty:
        new_df = df3m.copy()
        new_df["y10"] = None
    elif df3m.empty:
        new_df = df10.copy()
        new_df["y3m"] = None
    else:
        new_df = pd.merge(df10, df3m, on="date", how="outer")

    new_df["y10"]    = pd.to_numeric(new_df.get("y10"), errors="coerce")
    new_df["y3m"]    = pd.to_numeric(new_df.get("y3m"), errors="coerce")
    new_df["spread"] = (new_df["y10"] - new_df["y3m"]).round(3)

    combined = pd.concat([existing, new_df], ignore_index=True) if not existing.empty else new_df
    combined = (combined
                .drop_duplicates(subset=["date"])
                .sort_values("date")
                .reset_index(drop=True))

    market_dir.mkdir(parents=True, exist_ok=True)
    combined.to_csv(yields_path, index=False)
    log.info("us_yields 저장: %s (%d행)", yields_path, len(combined))
    return combined


def _percentile_threshold(series: pd.Series, pct: int, fallback: float) -> tuple[float, str]:
    vals = series.dropna()
    if len(vals) < 20:
        return fallback, "fallback"
    return float(vals.quantile(pct / 100)), "percentile"


def check_us_signals(vix_df: pd.DataFrame, yields_df: pd.DataFrame,
                     as_of: date | None = None,
                     lookback: int = LOOKBACK_TRADING_DAYS) -> dict:
    """역사적 퍼센타일 기반 미국 시장 시그널 판단.

    Returns:
        {
          'vix_signal': bool,
          'vix_value': float,
          'vix_threshold': float,
          'vix_pct_rank': float,
          'inversion_signal': bool,
          'spread': float,       # 10Y - 3M (%)
          'inversion_days': int, # 연속 역전일수
          'signals': list[str],
          'vix_data': dict,      # {date: float} — 차트용
          'yield_data': dict,    # {date: {y10, y3m, spread}} — 차트용
          'available': bool,
        }
    """
    today_str = (as_of or date.today()).strftime("%Y-%m-%d")
    result: dict = {
        "vix_signal": False, "vix_value": 0.0,
        "vix_threshold": 0.0, "vix_pct_rank": 50.0,
        "inversion_signal": False, "spread": 0.0, "inversion_days": 0,
        "signals": [], "vix_data": {}, "yield_data": {},
        "available": False,
    }

    if vix_df.empty and yields_df.empty:
        return result

    result["available"] = True

    # ── VIX ─────────────────────────────────────────────────────────────────
    if not vix_df.empty and "close" in vix_df.columns:
        hist = vix_df[vix_df["date"] <= today_str].tail(lookback)
        threshold, _ = _percentile_threshold(hist["close"], VIX_FEAR_PERCENTILE, 30.0)
        latest = hist.tail(1)
        if not latest.empty:
            val = float(latest.iloc[0]["close"])
            result["vix_value"] = val
            result["vix_threshold"] = threshold
            all_vals = hist["close"].dropna()
            pct_rank = float((all_vals < val).sum() / len(all_vals) * 100) if len(all_vals) > 0 else 50.0
            result["vix_pct_rank"] = round(pct_rank, 1)
            if val >= threshold:
                result["vix_signal"] = True
                result["signals"].append(
                    f"[⚠ VIX 공포] {latest.iloc[0]['date']}: "
                    f"{val:.1f} (역사적 상위 {100 - pct_rank:.0f}% — 기준: 상위 20%={threshold:.1f})"
                )
        # 차트용: 3개월치 (약 63 거래일)
        chart_hist = hist.tail(63)
        result["vix_data"] = {
            str(r["date"]): round(float(r["close"]), 2)
            for _, r in chart_hist.iterrows()
            if not pd.isna(r["close"])
        }

    # ── 수익률 곡선 ──────────────────────────────────────────────────────────
    if not yields_df.empty and "spread" in yields_df.columns:
        hist_y = yields_df[yields_df["date"] <= today_str].tail(lookback)
        latest_y = hist_y.tail(1)
        if not latest_y.empty:
            spread = float(pd.to_numeric(latest_y.iloc[0].get("spread"), errors="coerce") or 0)
            result["spread"] = round(spread, 3)
            # 연속 역전일수
            recent = hist_y.sort_values("date", ascending=False)
            consec = 0
            for _, row in recent.iterrows():
                s = float(pd.to_numeric(row.get("spread"), errors="coerce") or 0)
                if s < 0:
                    consec += 1
                else:
                    break
            result["inversion_days"] = consec
            if spread < 0:
                result["inversion_signal"] = True
                result["signals"].append(
                    f"[⚠ 수익률 역전] 10Y-3M spread: {spread:+.3f}% "
                    f"({consec}일 연속 역전 — 경기침체 선행 지표)"
                )
        # 차트용: 3개월치
        chart_y = hist_y.tail(63)
        result["yield_data"] = {
            str(r["date"]): {
                "y10":    (round(float(r["y10"]), 3)    if pd.notna(r.get("y10"))    else None),
                "y3m":    (round(float(r["y3m"]), 3)    if pd.notna(r.get("y3m"))    else None),
                "spread": (round(float(r["spread"]), 3) if pd.notna(r.get("spread")) else None),
            }
            for _, r in chart_y.iterrows()
        }

    result["any_signal"] = bool(result["signals"])
    return result


def run(data_dir: Path, end: date | None = None, verbose: bool = True) -> dict:
    """VIX + 미국채 수익률 수집 및 시그널 판단 진입점.

    증분 방식으로 동작.
    """
    if end is None:
        end = date.today()

    vix_df    = fetch_vix(data_dir, end)
    yields_df = fetch_us_yields(data_dir, end)
    signals   = check_us_signals(vix_df, yields_df, as_of=end)

    if verbose:
        print(f"\n=== 미국 시장 시그널 ({end}) ===")
        if not vix_df.empty:
            last5 = vix_df.tail(5)
            thr = signals.get("vix_threshold", 0)
            print(f"\n[VIX 최근 5일] (공포 기준: {thr:.1f} 이상)")
            for _, r in last5.iterrows():
                val = float(r["close"])
                flag = " ★공포" if val >= thr else ""
                print(f"  {r['date']}: {val:.2f}{flag}")
        if not yields_df.empty:
            last5 = yields_df.tail(5)
            print("\n[수익률 곡선 최근 5일]")
            for _, r in last5.iterrows():
                sp = r.get("spread")
                inv_flag = " ★역전" if (sp is not None and not pd.isna(sp) and float(sp) < 0) else ""
                y10 = r.get("y10"); y3m = r.get("y3m")
                print(f"  {r['date']}: 10Y={y10 if y10 else '—'} 3M={y3m if y3m else '—'} spread={sp if sp else '—'}%{inv_flag}")
        if signals["signals"]:
            print("\n[활성 시그널]")
            for msg in signals["signals"]:
                print(" ", msg)
        else:
            print("\n[시그널 없음] 현재 VIX·수익률 역전 경보 없음")

    return signals
