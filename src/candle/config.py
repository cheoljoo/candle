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
