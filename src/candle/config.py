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

    # 모든 type 고정 순서 (순서 변경 금지)
    ALL_TYPES: tuple[str, ...] = (
        "type1_1", "type1_2",
        "type2_1", "type2_2",
        "type2_1b", "type2_2b",
        "type3",
    )

    @property
    def enabled_types(self) -> list[str]:
        """config/strategies.yml의 enabled_types에 정의된 활성 type 목록.

        enabled_types 항목이 없으면 전체 7개 활성 (하위호환).
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


def load() -> Config:
    return Config(
        universe=_load_yaml("universe.yml"),
        strategies=_load_yaml("strategies.yml"),
        runtime=_load_yaml("runtime.yml"),
        recipients=_load_recipients(),
    )
