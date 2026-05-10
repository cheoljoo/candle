"""표준 경로 / 파일명 규칙."""
from __future__ import annotations

from pathlib import Path


def daily_csv(data_dir: Path, market: str, ticker: str) -> Path:
    return data_dir / "daily" / market / f"{ticker}.csv"


def instruments_csv(data_dir: Path) -> Path:
    return data_dir / "instruments.csv"


def membership_csv(data_dir: Path, group_name: str) -> Path:
    return data_dir / "universe" / f"{group_name.lower()}_membership.csv"


def etf_list_csv(data_dir: Path, market: str) -> Path:
    return data_dir / "universe" / f"etf_{market.lower()}.csv"


def dividends_csv(data_dir: Path) -> Path:
    return data_dir / "events" / "dividends.csv"


def analyze_dir(output_dir: Path, date: str) -> Path:
    return output_dir / "analyze" / date


def backtest_root(output_dir: Path, period: str | None = None) -> Path:
    """output/backtest/{period}/ 또는 output/backtest/ (period 없을 때)."""
    if period:
        return output_dir / "backtest" / period
    return output_dir / "backtest"


def backtest_dir(output_dir: Path, type_name: str, period: str | None = None) -> Path:
    """output/backtest/{period}/{type}/ 또는 output/backtest/{type}/."""
    return backtest_root(output_dir, period) / type_name


def compare_dir(output_dir: Path, period: str | None = None) -> Path:
    """output/compare/{period}/ 또는 output/compare/."""
    if period:
        return output_dir / "compare" / period
    return output_dir / "compare"


_KNOWN_TYPE_NAMES = {"type1_1", "type1_2", "type2_1", "type2_2", "type3"}


def list_backtest_periods(output_dir: Path) -> list[str]:
    """output/backtest/ 아래 period/label 디렉터리 목록 반환 (정렬).

    판별 기준: 그 디렉터리 안에 type 서브디렉터리(type1_1 등)가 있으면 period 디렉터리.
    - label 기반 ('5y', 'full') 과 날짜 기반 ('2020-01-01~') 모두 인식.
    - flat 구조(output/backtest/{type}/)는 제외.
    """
    bt_root = output_dir / "backtest"
    if not bt_root.exists():
        return []
    periods = sorted(
        p.name for p in bt_root.iterdir()
        if p.is_dir()
        and p.name not in _KNOWN_TYPE_NAMES
        and any((p / t).is_dir() for t in _KNOWN_TYPE_NAMES)
    )
    return periods


def list_compare_periods(output_dir: Path) -> list[str]:
    """output/compare/ 아래 label 디렉터리 목록 반환 (정렬).

    판별 기준: strategy_summary.csv 가 존재하는 서브디렉터리.
    """
    cmp_root = output_dir / "compare"
    if not cmp_root.exists():
        return []
    return sorted(
        p.name for p in cmp_root.iterdir()
        if p.is_dir() and (p / "strategy_summary.csv").exists()
    )
