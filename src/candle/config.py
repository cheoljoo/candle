"""YAML config loader (universe / strategies / runtime)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"


def _load_yaml(name: str) -> dict[str, Any]:
    p = CONFIG_DIR / name
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@dataclass
class Config:
    universe: dict[str, Any]
    strategies: dict[str, Any]
    runtime: dict[str, Any]
    recipients: dict[str, Any]
    periods: dict[str, Any] = None  # type: ignore[assignment]

    @property
    def ALL_TYPES(self) -> tuple[str, ...]:
        """strategies.yml에서 'type'으로 시작하는 모든 키 (YAML 정의 순서 유지).

        새 type 추가 시 strategies.yml에 항목을 추가하기만 하면 자동 반영됨.
        """
        return tuple(k for k in self.strategies if k.startswith("type"))

    @property
    def enabled_types(self) -> list[str]:
        """config/strategies.yml의 enabled_types에 정의된 활성 type 목록.

        enabled_types 항목이 없으면 ALL_TYPES 전체 활성 (하위호환).
        순서는 ALL_TYPES 정의 순서를 따름.
        """
        raw = self.strategies.get("enabled_types")
        if raw is None:
            return list(self.ALL_TYPES)
        enabled_set = set(raw)
        return [t for t in self.ALL_TYPES if t in enabled_set]

    @property
    def disabled_types(self) -> list[str]:
        """enabled_types에 없는 비활성 type 목록."""
        enabled = set(self.enabled_types)
        return [t for t in self.ALL_TYPES if t not in enabled]

    @property
    def backtest_periods(self) -> list[dict[str, Any]]:
        """config/periods.yml 의 periods 전체 목록."""
        if self.periods is None:
            return []
        return self.periods.get("periods", [])

    def backtest_periods_for_market(self, market: str) -> list[dict[str, Any]]:
        """market 에 해당하는 기간 목록만 반환.

        periods.yml 의 markets 필드 기준:
          all → make v2-backtest (전체 시장)
          kr  → make v2-backtest-kr
          us  → make v2-backtest-us
        """
        return [
            p for p in self.backtest_periods
            if market in p.get("markets", ["all", "kr", "us"])
        ]

    @property
    def repo_root(self) -> Path:
        return REPO_ROOT

    @property
    def data_dir(self) -> Path:
        return REPO_ROOT / self.runtime["paths"]["data"]

    @property
    def output_dir(self) -> Path:
        return REPO_ROOT / self.runtime["paths"]["output"]


def _load_recipients() -> dict[str, Any]:
    p = CONFIG_DIR / "recipients.yml"
    if not p.exists():
        return {"owner": "", "recipients": [], "dashboard_url": ""}
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_periods() -> dict[str, Any]:
    p = CONFIG_DIR / "periods.yml"
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load() -> Config:
    return Config(
        universe=_load_yaml("universe.yml"),
        strategies=_load_yaml("strategies.yml"),
        runtime=_load_yaml("runtime.yml"),
        recipients=_load_recipients(),
        periods=_load_periods(),
    )
