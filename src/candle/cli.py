"""candle CLI 진입점."""
from __future__ import annotations

import logging
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import typer

from . import config


app = typer.Typer(add_completion=False, no_args_is_help=True, help="candle backtest pipeline")


def _setup_logging(cfg: config.Config, debug: bool = False) -> None:
    lv = cfg.runtime.get("logging", {}).get("level", "INFO")
    logging.basicConfig(
        level=getattr(logging, lv, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )
    # --debug 는 candle 자체의 print() 디버그 로그만 켠다 (외부 라이브러리 DEBUG 로그는 무관).


def _today(s: Optional[str]) -> date:
    if s:
        return datetime.strptime(s, "%Y-%m-%d").date()
    return date.today()


def _maybe_date(s: Optional[str]) -> Optional[date]:
    return datetime.strptime(s, "%Y-%m-%d").date() if s else None


def _make_period(from_str: Optional[str], to_str: Optional[str]) -> Optional[str]:
    """CLI --from/--to 문자열 → 디렉터리 이름용 period 문자열.

    --from 2020-01-01           → "2020-01-01~"
    --from 2020-01-01 --to 2024 → "2020-01-01~2024-12-31"
    둘 다 없음                  → None (flat 구조)
    """
    if not from_str:
        return None
    return f"{from_str}~{to_str}" if to_str else f"{from_str}~"


@app.command()
def universe(
    market: str = typer.Option("all", help="kr | us | all"),
    small: bool = typer.Option(False, "--small", help="dev용 작은 universe만 빌드"),
    today: Optional[str] = typer.Option(None, help="기준일 YYYY-MM-DD"),
    debug: bool = typer.Option(False, "--debug", help="단계/그룹별 진행 상황 상세 출력"),
):
    """universe (KOSPI200 / S&P500 / ETF) 갱신."""
    cfg = config.load()
    _setup_logging(cfg, debug=debug)
    from .universe import build
    counts = build.update(cfg, _today(today), small=small, debug=debug)
    typer.echo(f"universe updated: {counts}")


@app.command()
def fetch(
    market: str = typer.Option("all", help="kr | us | all"),
    today: Optional[str] = typer.Option(None, help="기준일 YYYY-MM-DD"),
    debug: bool = typer.Option(False, "--debug", help="회사별 fetch start/end 상세 출력"),
    workers: int = typer.Option(4, "--workers", help="병렬 fetch worker 수 (기본 4)"),
    timeout: int = typer.Option(10, "--timeout", help="종목당 timeout 초 (기본 10) — 초과 시 fail 처리"),
    from_str: Optional[str] = typer.Option(None, "--from", help="백필 시작일 YYYY-MM-DD — 기존 파일이 있어도 이 날짜부터 재수집"),
):
    """일봉 + 펀더멘털 + 배당 증분 fetch."""
    cfg = config.load()
    _setup_logging(cfg, debug=debug)
    from .fetch import run as fetch_run
    res = fetch_run.run(cfg, market, _today(today),
                        debug=debug, workers=workers, timeout=timeout,
                        from_date=_maybe_date(from_str))
    typer.echo(f"fetch result: {res}")


@app.command()
def analyze(
    market: str = typer.Option("all", help="kr | us | all"),
    today: Optional[str] = typer.Option(None, help="기준일 YYYY-MM-DD"),
    debug: bool = typer.Option(False, "--debug", help="회사별 analyze start/end 상세 출력"),
    refresh: bool = typer.Option(False, "--refresh",
                                  help="skip 무시 + 전체 행 재계산 (--from 백필 직후 1회 실행)"),
):
    """지표 + 변곡점 + 시총 순위 채우기."""
    cfg = config.load()
    _setup_logging(cfg, debug=debug)
    from .analyze import run as analyze_run
    res = analyze_run.run(cfg, market, _today(today), debug=debug, refresh=refresh)
    typer.echo(f"analyze result: {res}")


@app.command()
def backtest(
    types: str = typer.Option("type1_1,type1_2,type2_1,type2_2,type2_1b,type2_2b,type3",
                              help="콤마 분리. 예: type1_1,type3"),
    market: str = typer.Option("all", help="kr | us | all"),
    start: Optional[str] = typer.Option(None, "--from", help="시작일 YYYY-MM-DD"),
    end: Optional[str] = typer.Option(None, "--to", help="종료일 YYYY-MM-DD"),
    label: Optional[str] = typer.Option(None, "--label",
                                         help="출력 디렉터리 이름 (날짜 대신 고정 레이블). "
                                              "예: --label 5y  → output/backtest/5y/{type}/. "
                                              "내년에도 같은 디렉터리를 갱신하고 싶을 때 사용."),
    debug: bool = typer.Option(False, "--debug", help="type×ticker별 backtest 진행 상황 출력"),
):
    """backtest 5종 (또는 일부) 실행.

    출력 디렉터리 결정 우선순위:
      --label 5y                  → output/backtest/5y/{type}/        (레이블 고정)
      --from 2020-01-01           → output/backtest/2020-01-01~/{type}/
      --from 2020-01-01 --to 2024 → output/backtest/2020-01-01~2024-12-31/{type}/
      옵션 없음                   → output/backtest/{type}/           (flat)
    """
    cfg = config.load()
    _setup_logging(cfg, debug=debug)
    from .backtest import run as bt_run
    type_list = [t.strip() for t in types.split(",") if t.strip()]
    period = label if label else _make_period(start, end)
    res = bt_run.run(cfg, type_list, market, _maybe_date(start), _maybe_date(end),
                     debug=debug, period=period)
    typer.echo(f"backtest result: {res}")


@app.command()
def compare(
    types: str = typer.Option("type1_1,type1_2,type2_1,type2_2,type2_1b,type2_2b,type3",
                              help="비교할 backtest type 리스트 (콤마 분리)"),
    start: Optional[str] = typer.Option(None, "--from", help="backtest --from 과 동일 값"),
    end: Optional[str] = typer.Option(None, "--to", help="backtest --to 와 동일 값"),
    label: Optional[str] = typer.Option(None, "--label",
                                         help="backtest --label 과 동일 값 (예: 5y, full). "
                                              "backtest 와 같은 레이블을 줘야 같은 디렉터리를 읽음."),
    debug: bool = typer.Option(False, "--debug", help="단계별 입력 로딩/계산 진행 출력"),
):
    """backtest 결과 비교 (전략별 + 종목별 cross + 최고전략).

    backtest 와 동일한 --label (또는 --from/--to) 을 지정해야 같은 기간 디렉터리를 읽습니다.
    """
    cfg = config.load()
    _setup_logging(cfg, debug=debug)
    from .compare import run as cmp_run
    type_list = [t.strip() for t in types.split(",") if t.strip()]
    period = label if label else _make_period(start, end)
    res = cmp_run.run(cfg, type_list, debug=debug, period=period)
    typer.echo(f"compare result: {res}")


@app.command()
def simulate(
    today: Optional[str] = typer.Option(None, help="기준일 YYYY-MM-DD"),
    use_ai: bool = typer.Option(True, "--ai/--no-ai", help="Claude API 사용 여부 (기본 ON, ANTHROPIC_API_KEY 없으면 자동 skip)"),
    debug: bool = typer.Option(False, "--debug", help="회사별 rule/AI 의사결정 진행 상황 출력"),
):
    """매일 1회 의사결정 (rule + AI + manual) → decisions.csv + trades.csv."""
    cfg = config.load()
    _setup_logging(cfg, debug=debug)
    from .simulate import run as sim_run
    res = sim_run.run(cfg, _today(today), use_ai=use_ai, debug=debug)
    typer.echo(f"simulate result: {res}")


@app.command()
def dashboard(
    today: Optional[str] = typer.Option(None, help="기준일 YYYY-MM-DD"),
    out: Optional[str] = typer.Option(None, help="출력 디렉터리 (기본 dashboard_site/)"),
    debug: bool = typer.Option(False, "--debug", help="ticker별 변곡점 lookup 진행 출력"),
):
    """static HTML dashboard 생성."""
    cfg = config.load()
    _setup_logging(cfg, debug=debug)
    from .dashboard import render as dash
    out_path = Path(out) if out else None
    res = dash.render(cfg, _today(today), out_dir=out_path, debug=debug)
    typer.echo(f"dashboard: {res}")


@app.command("optimize-streak")
def optimize_streak(
    market:     str  = typer.Option("all",  help="kr | us | all"),
    all_groups: bool = typer.Option(False, "--all-groups",
                                    help="전체 + 4개 그룹별 결과를 한번에 생성 (--output-dir 디렉터리에 저장)"),
    output_dir: Optional[str] = typer.Option(None, "--output-dir",
                                              help="--all-groups 시 저장 디렉터리 (기본 output/optimize/)"),
    start:      Optional[str] = typer.Option(None, "--from",       help="시작일 YYYY-MM-DD"),
    end:        Optional[str] = typer.Option(None, "--to",         help="종료일 YYYY-MM-DD"),
    plus_min:   int = typer.Option(4,  "--plus-min",  help="plus_days 최솟값 (기본 4)"),
    plus_max:   int = typer.Option(40, "--plus-max",  help="plus_days 최댓값 (기본 40)"),
    plus_step:  int = typer.Option(2,  "--plus-step", help="plus_days 간격 (기본 2)"),
    minus_min:  int = typer.Option(4,  "--minus-min", help="minus_days 최솟값 (기본 4)"),
    minus_max:  int = typer.Option(10, "--minus-max", help="minus_days 최댓값 (기본 10)"),
    minus_step: int = typer.Option(2,  "--minus-step",help="minus_days 간격 (기본 2)"),
    workers:    int  = typer.Option(4,  "--workers",   help="ticker 로딩 병렬 worker 수 (기본 4)"),
    top_n:      int  = typer.Option(30, "--top",       help="상위 N개 출력 (기본 30)"),
    output:     Optional[str] = typer.Option(None, "--output", help="단일 결과 저장 CSV 경로 (--all-groups 미사용 시)"),
    debug:      bool = typer.Option(False, "--debug",
                                    help="ticker별 로딩 결과 + 조합별 즉시 수익률 출력"),
):
    """plus_days / minus_days 그리드 서치 — type2_1b / type2_2b 최적 연속일수 탐색.

    type2 전략 (연속일수 신호)의 plus_days / minus_days 를 바꿔가며
    718개 전 종목에 대한 시뮬레이션을 수행, avg_return 이 가장 높은 조합을 찾습니다.

    --all-groups: 전체(all) + KOSPI200 / SP500 / ETF_KR / ETF_US 5개 결과 파일 생성
    --debug: ticker별 로딩 현황 + (plus, minus) 조합별 결과를 즉시 출력
    """
    cfg = config.load()
    from .optimize.streak_grid import run as sg_run, run_all_groups
    from pathlib import Path as _Path

    kwargs = dict(
        start=_maybe_date(start), end=_maybe_date(end),
        plus_min=plus_min, plus_max=plus_max, plus_step=plus_step,
        minus_min=minus_min, minus_max=minus_max, minus_step=minus_step,
        workers=workers, top_n=top_n, debug=debug,
    )

    if all_groups:
        out_d = _Path(output_dir) if output_dir else cfg.output_dir / "optimize"
        run_all_groups(cfg, output_dir=out_d, **kwargs)
    else:
        out_path = _Path(output) if output else None
        sg_run(cfg, market=market, output_csv=out_path, **kwargs)


def main():
    app()


if __name__ == "__main__":
    main()
