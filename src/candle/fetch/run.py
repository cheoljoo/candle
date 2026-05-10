"""Fetch 진입 루틴 — instruments.csv를 돌면서 ticker별 일봉 증분 적재.

성능:
- KR: pykrx ticker별 직렬 호출 → ThreadPoolExecutor 로 N개 병렬.
- US: yfinance batch download (window 별 묶음) + 펀더멘털/배당은 thread pool.
- 종목당 timeout 은 `socket.setdefaulttimeout()` 으로 적용 — 그 이상 걸리면
  socket.timeout 으로 raise 되어 "fail" 처리되고 다음 종목으로 진행.
"""
from __future__ import annotations

import logging
import socket
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import pandas as pd

from .. import config
from ..io_report import announce, tprint
from ..storage import csv_io, incremental, paths
from . import kr, us

log = logging.getLogger(__name__)


def _patch_requests_timeout(timeout: float) -> None:
    """모든 requests.Session.request 호출에 default timeout 강제 주입.

    `socket.setdefaulttimeout()` 은 connection pool 에 이미 존재하는 소켓이나
    requests 의 일부 경로에서는 무시되는 경우가 있어, 호출자가 timeout 을
    명시 안 한 경우(또는 None) 우리 default 로 덮어씌운다.
    """
    try:
        import requests.sessions as rs
    except ImportError:
        return
    if getattr(rs.Session.request, "_candle_patched", False):
        # 이미 patch 됨 — timeout 만 갱신
        rs.Session.request._candle_timeout = timeout  # type: ignore[attr-defined]
        return
    orig = rs.Session.request

    def _wrapped(self, method, url, **kwargs):
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = _wrapped._candle_timeout
        return orig(self, method, url, **kwargs)

    _wrapped._candle_patched = True  # type: ignore[attr-defined]
    _wrapped._candle_timeout = timeout  # type: ignore[attr-defined]
    rs.Session.request = _wrapped


def _print_ticker_chunks(label: str, tickers: list[str], per_line: int = 20) -> None:
    """디버그용으로 ticker 목록을 청크 단위 한 줄씩 출력."""
    for i in range(0, len(tickers), per_line):
        chunk = tickers[i:i + per_line]
        print(f"[fetch][debug] {label} tickers [{i+1}-{i+len(chunk)}/{len(tickers)}]: {', '.join(chunk)}", flush=True)


def run(cfg: config.Config, market: str, today: date,
        debug: bool = False, workers: int = 4, timeout: int = 10,
        from_date: date | None = None) -> dict[str, int]:
    announce(
        f"fetch --market {market}",
        inputs=[
            ("data/instruments.csv",
             "fetch 대상 ticker 목록 (universe build 산출)"),
            ("data/daily/{KR|US}/{ticker}.csv (있으면)",
             "기존 일봉 — 마지막 date 다음 거래일부터만 증분 fetch"),
        ],
        outputs=[
            ("data/daily/KR/{ticker}.csv",
             "KR 일봉 — date, open, high, low, close, volume, per, pbr, shares_out, market_cap (pykrx)"),
            ("data/daily/US/{ticker}.csv",
             "US 일봉 — 동일 스키마, PER/PBR/시총은 마지막 row 스냅샷만 (yfinance)"),
            ("data/events/dividends.csv",
             "배당 이벤트 (US) — ticker,event_date,amount,yield_pct,payout_ratio"),
        ],
    )
    socket.setdefaulttimeout(float(timeout))
    _patch_requests_timeout(float(timeout))

    # config에서 history_start 읽기
    _hs_str = cfg.runtime.get("fetch", {}).get("history_start")
    history_start: date | None = None
    if _hs_str:
        from datetime import datetime as _dt
        history_start = _dt.strptime(str(_hs_str), "%Y-%m-%d").date()

    if from_date is not None:
        if debug:
            print(f"[fetch][debug] workers={workers} timeout={timeout}s — from_date={from_date} (백필 모드: 기존 파일도 이 날짜부터)", flush=True)
    else:
        if debug:
            eff_start = f"history_start={history_start}" if history_start else f"today-{cfg.runtime['fetch']['default_history_days']}d"
            print(f"[fetch][debug] workers={workers} timeout={timeout}s — 신규 ticker 기준 start: {eff_start}", flush=True)

    inst = csv_io.read(paths.instruments_csv(cfg.data_dir))
    if inst.empty:
        log.warning("instruments.csv가 비어 있음. universe build 먼저 실행")
        return {"fetched": 0}

    if market != "all":
        inst = inst[inst["market"] == market.upper()]

    history_days = int(cfg.runtime["fetch"]["default_history_days"])
    fetched = 0
    skipped = 0
    failed: list[str] = []
    div_frames: list[pd.DataFrame] = []

    kr_rows = [r for _, r in inst.iterrows() if str(r["market"]) == "KR"]
    us_rows = [r for _, r in inst.iterrows() if str(r["market"]) == "US"]

    if kr_rows:
        f, s, fa = _fetch_kr(cfg, kr_rows, history_days, today, workers, debug,
                             from_date=from_date, history_start=history_start)
        fetched += f; skipped += s; failed.extend(fa)

    if us_rows:
        f, s, fa, divs = _fetch_us_batch(cfg, us_rows, history_days, today, workers, debug,
                                          from_date=from_date, history_start=history_start)
        fetched += f; skipped += s; failed.extend(fa); div_frames.extend(divs)

    if div_frames:
        all_div = pd.concat(div_frames, ignore_index=True)
        csv_io.upsert_by_keys(
            paths.dividends_csv(cfg.data_dir), all_div,
            key_cols=["ticker", "event_date"],
            sort_cols=["ticker", "event_date"],
            overwrite=False,
        )

    return {"fetched": fetched, "skipped": skipped, "failed": len(failed),
            "failed_tickers": failed[:10]}


# ── KR ─────────────────────────────────────────────────────────────────
def _fetch_kr(cfg: config.Config, rows: list, history_days: int,
              today: date, workers: int, debug: bool,
              from_date: date | None = None,
              history_start: date | None = None) -> tuple[int, int, list[str]]:
    """KR fetch: yfinance batch(.KS) → .KQ retry → pykrx fallback."""
    fetched, skipped = 0, 0
    failed: list[str] = []

    # ── window 계산 & skip ──────────────────────────────────────────
    tasks: list[tuple[str, str, object, date, date]] = []
    for row in rows:
        ticker = str(row["ticker"])
        group = str(row["group_name"])
        path = paths.daily_csv(cfg.data_dir, "KR", ticker)
        start, end = incremental.fetch_window(path, history_days, today,
                                              from_date=from_date, history_start=history_start)
        if start > end:
            skipped += 1
            if debug:
                print(f"[fetch][debug] KR/{ticker} ({group}) skip — up-to-date (last>={end})", flush=True)
            continue
        tasks.append((ticker, group, path, start, end))

    if not tasks:
        return fetched, skipped, failed

    total = len(tasks)

    # ── Step 1: yfinance batch .KS ──────────────────────────────────
    ohlcv: dict[str, pd.DataFrame] = {}
    if debug:
        print(f"[fetch][debug] KR yfinance batch 시작 — {total}개", flush=True)

    by_window: dict[tuple[date, date], list] = defaultdict(list)
    for t in tasks:
        by_window[(t[3], t[4])].append(t)

    for (start, end), group_tasks in by_window.items():
        tickers = [t[0] for t in group_tasks]
        yf_tickers = kr.to_yf_tickers(tickers, ".KS")
        if debug:
            print(f"[fetch][debug] KR batch .KS window {start}..{end} — {len(tickers)} tickers", flush=True)
            _print_ticker_chunks("KR batch .KS", tickers)
        t0 = time.perf_counter()
        try:
            result = us.fetch_daily_batch(yf_tickers, start, end)
            stripped = kr.strip_yf_suffix(result, ".KS")
            ohlcv.update(stripped)
            if debug:
                hit = sum(1 for v in stripped.values() if not v.empty)
                print(f"[fetch][debug] KR batch .KS end ({time.perf_counter()-t0:.2f}s) — rows for {hit}/{len(tickers)}", flush=True)
        except Exception as e:
            log.warning(f"KR batch .KS 실패 {start}..{end}: {e}")
            if debug:
                print(f"[fetch][debug] KR batch .KS FAIL ({time.perf_counter()-t0:.2f}s): {e}", flush=True)

    # ── Step 2: .KQ retry (빈 것만) ─────────────────────────────────
    kq_tasks = [t for t in tasks if ohlcv.get(t[0], pd.DataFrame()).empty]
    if kq_tasks:
        by_window_kq: dict[tuple[date, date], list] = defaultdict(list)
        for t in kq_tasks:
            by_window_kq[(t[3], t[4])].append(t)
        for (start, end), group_tasks in by_window_kq.items():
            tickers = [t[0] for t in group_tasks]
            yf_tickers = kr.to_yf_tickers(tickers, ".KQ")
            if debug:
                print(f"[fetch][debug] KR batch .KQ window {start}..{end} — {len(tickers)} tickers", flush=True)
                _print_ticker_chunks("KR batch .KQ", tickers)
            t0 = time.perf_counter()
            try:
                result = us.fetch_daily_batch(yf_tickers, start, end)
                stripped = kr.strip_yf_suffix(result, ".KQ")
                for tk, df in stripped.items():
                    if not df.empty:
                        ohlcv[tk] = df
                if debug:
                    hit = sum(1 for v in stripped.values() if not v.empty)
                    print(f"[fetch][debug] KR batch .KQ end ({time.perf_counter()-t0:.2f}s) — rows for {hit}/{len(tickers)}", flush=True)
            except Exception as e:
                log.warning(f"KR batch .KQ 실패 {start}..{end}: {e}")
                if debug:
                    print(f"[fetch][debug] KR batch .KQ FAIL ({time.perf_counter()-t0:.2f}s): {e}", flush=True)

    # ── Step 3: 스냅샷 펀더멘털 (yfinance 성공 ticker) ───────────────
    yf_ok_tasks = [t for t in tasks if not ohlcv.get(t[0], pd.DataFrame()).empty]
    if yf_ok_tasks:
        if debug:
            print(f"[fetch][debug] KR fast_info thread pool — {len(yf_ok_tasks)}개, workers={workers}", flush=True)

        def _kr_info(t):
            ticker = t[0]
            # 어떤 suffix로 받았는지 역추적
            for suffix in (".KS", ".KQ"):
                yf_tk = ticker + suffix
                try:
                    import yfinance as yf
                    info = yf.Ticker(yf_tk).fast_info
                    per = getattr(info, "trailing_pe", None)
                    so = getattr(info, "shares", None)
                    mc = getattr(info, "market_cap", None) or getattr(info, "marketCap", None)
                    if per is not None or mc is not None:
                        return t, per, so, mc
                except Exception:
                    pass
            return t, None, None, None

        per_task_timeout = socket.getdefaulttimeout() or 10.0
        info_deadline = time.monotonic() + max(60.0, per_task_timeout * len(yf_ok_tasks) / max(workers, 1) * 2 + per_task_timeout)
        info_map: dict[str, tuple] = {}
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs_info = [ex.submit(_kr_info, t) for t in yf_ok_tasks]
            fut_to_task_info = dict(zip(futs_info, yf_ok_tasks))
            try:
                for fut in as_completed(futs_info, timeout=info_deadline - time.monotonic()):
                    t, per, so, mc = fut.result()
                    info_map[t[0]] = (per, so, mc)
            except Exception as e:
                log.warning(f"KR fast_info timeout/error: {e}")
            for fut, t in fut_to_task_info.items():
                if not fut.done():
                    info_map.setdefault(t[0], (None, None, None))
                    fut.cancel()

        # 펀더멘털을 ohlcv df에 병합
        for ticker, df in ohlcv.items():
            if df.empty:
                continue
            per, so, mc = info_map.get(ticker, (None, None, None))
            df["per"] = pd.NA
            df["pbr"] = pd.NA
            df["shares_out"] = pd.NA
            df["market_cap"] = pd.NA
            if not df.empty and (per is not None or mc is not None or so is not None):
                last = df.index[-1]
                if per is not None:
                    df.at[last, "per"] = per
                if so is not None:
                    df.at[last, "shares_out"] = so
                if mc is not None:
                    df.at[last, "market_cap"] = mc
            ohlcv[ticker] = df

    # ── Step 4: pykrx fallback (여전히 빈 ticker) ────────────────────
    pykrx_tasks = [t for t in tasks if ohlcv.get(t[0], pd.DataFrame()).empty]
    if pykrx_tasks:
        if debug:
            print(f"[fetch][debug] KR pykrx fallback — {len(pykrx_tasks)}개, workers={workers}", flush=True)
            _print_ticker_chunks("KR pykrx", [t[0] for t in pykrx_tasks])

        def _do_pykrx(t):
            ticker, group, path, start, end = t
            if debug:
                print(f"[fetch][debug] KR/{ticker} ({group}) pykrx fetching... window={start}..{end}", flush=True)
            t0 = time.perf_counter()
            try:
                if group == "ETF_KR":
                    df = kr.fetch_etf_daily_pykrx(ticker, start, end)
                else:
                    df = kr.fetch_daily_pykrx(ticker, start, end)
                return ("ok", t, df, time.perf_counter() - t0, None)
            except Exception as e:
                return ("err", t, None, time.perf_counter() - t0, e)

        per_task_timeout = socket.getdefaulttimeout() or 10.0
        pykrx_deadline = time.monotonic() + max(60.0, per_task_timeout * (len(pykrx_tasks) / max(workers, 1)) * 2 + per_task_timeout)
        last_progress = time.monotonic()
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs_p = [ex.submit(_do_pykrx, t) for t in pykrx_tasks]
            fut_to_task_p = dict(zip(futs_p, pykrx_tasks))
            i_p = 0
            try:
                for fut in as_completed(futs_p, timeout=pykrx_deadline - time.monotonic()):
                    i_p += 1
                    now = time.monotonic()
                    if debug and (now - last_progress) > 30:
                        pending = [fut_to_task_p[f][0] for f in futs_p if not f.done()]
                        print(f"[fetch][debug] KR pykrx heartbeat — {len(pending)}개 진행 중: {', '.join(pending[:8])}{'...' if len(pending) > 8 else ''}", flush=True)
                    last_progress = now
                    status, t, df, dt, err = fut.result()
                    ticker, group, *_ = t
                    if status == "err":
                        log.warning(f"fetch {ticker} 실패: {err}")
                        failed.append(ticker)
                        if debug:
                            print(f"[fetch][debug] ({i_p}/{len(pykrx_tasks)}) KR/{ticker} ({group}) pykrx FAIL ({dt:.2f}s): {err}", flush=True)
                        continue
                    if df is not None and not df.empty:
                        ohlcv[ticker] = df
                        if debug:
                            print(f"[fetch][debug] ({i_p}/{len(pykrx_tasks)}) KR/{ticker} ({group}) pykrx end ({dt:.2f}s) — rows={len(df)}", flush=True)
                    else:
                        if debug:
                            print(f"[fetch][debug] ({i_p}/{len(pykrx_tasks)}) KR/{ticker} ({group}) pykrx end ({dt:.2f}s) — empty", flush=True)
            except Exception as e:
                log.warning(f"KR pykrx 전체 timeout/error: {e}")
            for fut, t in fut_to_task_p.items():
                if fut.done():
                    continue
                ticker, group, *_ = t
                failed.append(ticker)
                fut.cancel()
                if debug:
                    print(f"[fetch][debug] KR/{ticker} ({group}) pykrx TIMEOUT", flush=True)

    # ── Step 5: CSV 저장 ─────────────────────────────────────────────
    for i, t in enumerate(tasks, start=1):
        ticker, group, path, start, end = t
        df = ohlcv.get(ticker)
        if df is None or df.empty:
            skipped += 1
            continue
        csv_io.upsert_by_keys(
            path, df,
            key_cols=["date"], sort_cols=["date"], overwrite=False,
        )
        fetched += 1
        if debug:
            print(f"[fetch][debug] ({i}/{total}) KR/{ticker} saved — rows={len(df)}", flush=True)

    return fetched, skipped, failed


# ── US ─────────────────────────────────────────────────────────────────
# 큰 batch (수백 ticker) 를 yfinance 한 번에 보내면 wall-clock 이 들쭉날쭉
# (관측: 510개 → 46s ~ 145s). chunk 로 쪼개 병렬 호출하면:
#   - 한 chunk 가 stall 해도 다른 chunk 는 진행 (꼬리 latency 감소)
#   - 진행 가시성 (chunk 단위 완료 로그)
#   - 실패 격리 (chunk 단위 retry 가능)
# 단 Yahoo rate-limit 때문에 동시 chunk 수는 작게 유지.
US_BATCH_CHUNK_SIZE = 80
US_BATCH_PARALLEL = 3


def _us_batch_download_chunked(
    tickers: list[str], start: date, end: date,
    debug: bool, label: str = "US batch",
) -> dict[str, pd.DataFrame]:
    """tickers 를 작은 chunk 로 쪼개 yfinance batch 를 병렬 호출."""
    if len(tickers) <= US_BATCH_CHUNK_SIZE:
        return us.fetch_daily_batch(tickers, start, end)

    chunks = [tickers[i:i + US_BATCH_CHUNK_SIZE]
              for i in range(0, len(tickers), US_BATCH_CHUNK_SIZE)]
    parallel = min(US_BATCH_PARALLEL, len(chunks))
    if debug:
        print(f"[fetch][debug] {label} chunked — {len(chunks)} chunks × ~{US_BATCH_CHUNK_SIZE}, parallel={parallel}", flush=True)

    result: dict[str, pd.DataFrame] = {}
    with ThreadPoolExecutor(max_workers=parallel) as ex:
        futs = {ex.submit(us.fetch_daily_batch, ch, start, end): (i, ch)
                for i, ch in enumerate(chunks, 1)}
        for fut in as_completed(futs):
            idx, ch = futs[fut]
            try:
                r = fut.result()
                result.update(r)
                if debug:
                    hit = sum(1 for v in r.values() if not v.empty)
                    print(f"[fetch][debug] {label} chunk {idx}/{len(chunks)} done — {hit}/{len(ch)}", flush=True)
            except Exception as e:
                log.warning(f"{label} chunk {idx} 실패: {e}")
                if debug:
                    print(f"[fetch][debug] {label} chunk {idx}/{len(chunks)} FAIL: {e}", flush=True)
                for tk in ch:
                    result.setdefault(tk, pd.DataFrame())
    return result


def _fetch_us_batch(cfg: config.Config, rows: list, history_days: int,
                    today: date, workers: int, debug: bool,
                    from_date: date | None = None,
                    history_start: date | None = None,
                    ) -> tuple[int, int, list[str], list[pd.DataFrame]]:
    fetched, skipped = 0, 0
    failed: list[str] = []
    div_frames: list[pd.DataFrame] = []
    t_us_start = time.perf_counter()

    tasks: list[tuple[str, str, "Path", date, date]] = []
    for row in rows:
        ticker = str(row["ticker"])
        group = str(row["group_name"])
        path = paths.daily_csv(cfg.data_dir, "US", ticker)
        start, end = incremental.fetch_window(path, history_days, today,
                                              from_date=from_date, history_start=history_start)
        if start > end:
            skipped += 1
            if debug:
                print(f"[fetch][debug] US/{ticker} ({group}) skip — up-to-date (last>={end})")
            continue
        tasks.append((ticker, group, path, start, end))

    if not tasks:
        return fetched, skipped, failed, div_frames

    total = len(tasks)
    if debug:
        print(f"[fetch][debug] US batch fetch 시작 — {total}개")

    # ── Phase 1: yf.download batch (window 별, chunk 병렬) ──────────────
    t_phase1 = time.perf_counter()
    by_window: dict[tuple[date, date], list[tuple]] = defaultdict(list)
    for t in tasks:
        by_window[(t[3], t[4])].append(t)

    ohlcv_per_ticker: dict[str, pd.DataFrame] = {}
    for (start, end), group_tasks in by_window.items():
        tickers_in_window = [t[0] for t in group_tasks]
        if debug:
            print(f"[fetch][debug] US batch download window {start}..{end} — {len(tickers_in_window)} tickers")
            _print_ticker_chunks("US batch", tickers_in_window)
        t0 = time.perf_counter()
        try:
            result = _us_batch_download_chunked(tickers_in_window, start, end, debug)
            ohlcv_per_ticker.update(result)
            hit = sum(1 for v in result.values() if not v.empty)
            tprint(f"[fetch] US batch window {start}..{end}: {time.perf_counter()-t0:.2f}s "
                   f"({hit}/{len(tickers_in_window)} rows received)", flush=True)
        except Exception as e:
            log.warning(f"US batch fetch 실패 {start}..{end}: {e}")
            tprint(f"[fetch] US batch window {start}..{end} FAIL ({time.perf_counter()-t0:.2f}s): {e}", flush=True)
    phase1_dt = time.perf_counter() - t_phase1

    # ── Phase 2: per-ticker 펀더멘털/배당 — thread pool ─────────────────
    t_phase2 = time.perf_counter()
    if debug:
        print(f"[fetch][debug] US 펀더멘털/배당 thread pool — {total}개, workers={workers}")
        _print_ticker_chunks("US info", [t[0] for t in tasks])

    def _info(idx, t):
        ticker = t[0]
        if debug:
            print(f"[fetch][debug] ({idx}/{total}) US/{ticker} info fetching...", flush=True)
        t0 = time.perf_counter()
        try:
            per, shares_out, market_cap = us.fetch_fast_info(ticker)
        except Exception:
            per, shares_out, market_cap = None, None, None
        try:
            div = us.fetch_dividends(ticker)
        except Exception:
            div = pd.DataFrame()
        return t, per, shares_out, market_cap, div, time.perf_counter() - t0

    info_map: dict[str, tuple] = {}
    per_task_timeout = socket.getdefaulttimeout() or 10.0
    overall_deadline = time.monotonic() + max(60.0, per_task_timeout * (total / max(workers, 1)) * 2 + per_task_timeout)
    last_progress = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_info, i, t) for i, t in enumerate(tasks, 1)]
        fut_to_task = dict(zip(futs, tasks))
        try:
            for fut in as_completed(futs, timeout=overall_deadline - time.monotonic()):
                now = time.monotonic()
                if debug and (now - last_progress) > 30:
                    pending = [fut_to_task[f][0] for f in futs if not f.done()]
                    print(f"[fetch][debug] US info heartbeat — {len(pending)}개 진행 중: {', '.join(pending[:8])}{'...' if len(pending) > 8 else ''}", flush=True)
                last_progress = now
                t, per, so, mc, div, dt = fut.result()
                info_map[t[0]] = (per, so, mc)
                if div is not None and not div.empty:
                    div_frames.append(div)
        except Exception as e:
            log.warning(f"US info 전체 timeout/error: {e}")
        for fut, t in fut_to_task.items():
            if fut.done():
                continue
            ticker = t[0]
            info_map.setdefault(ticker, (None, None, None))
            fut.cancel()
            if debug:
                print(f"[fetch][debug] US/{ticker} info TIMEOUT (deadline 초과, cancel)", flush=True)
    phase2_dt = time.perf_counter() - t_phase2

    # ── Phase 3: 결과 합쳐 csv 저장 ─────────────────────────────────────
    t_phase3 = time.perf_counter()
    for i, t in enumerate(tasks, start=1):
        ticker, group, path, start, end = t
        t0 = time.perf_counter()
        df = ohlcv_per_ticker.get(ticker)
        if df is None or df.empty:
            skipped += 1
            if debug:
                print(f"[fetch][debug] ({i}/{total}) US/{ticker} ({group}) end ({time.perf_counter()-t0:.2f}s) — empty")
            continue
        per, so, mc = info_map.get(ticker, (None, None, None))
        df = df.copy()
        df["per"] = pd.NA
        df["pbr"] = pd.NA
        df["shares_out"] = pd.NA
        df["market_cap"] = pd.NA
        if not df.empty and (per is not None or mc is not None or so is not None):
            last_idx = df.index[-1]
            if per is not None:
                df.at[last_idx, "per"] = per
            if so is not None:
                df.at[last_idx, "shares_out"] = so
            if mc is not None:
                df.at[last_idx, "market_cap"] = mc
        df = df[["date", "open", "high", "low", "close", "volume",
                 "per", "pbr", "shares_out", "market_cap"]]
        csv_io.upsert_by_keys(
            path, df,
            key_cols=["date"], sort_cols=["date"], overwrite=False,
        )
        fetched += 1
        if debug:
            print(f"[fetch][debug] ({i}/{total}) US/{ticker} ({group}) end ({time.perf_counter()-t0:.2f}s) — rows={len(df)}")
    phase3_dt = time.perf_counter() - t_phase3

    total_dt = time.perf_counter() - t_us_start
    tprint(f"[fetch] US summary — {total} tickers in {total_dt:.2f}s "
           f"(batch_dl {phase1_dt:.2f}s / fast_info+div {phase2_dt:.2f}s / save {phase3_dt:.2f}s)",
           flush=True)

    return fetched, skipped, failed, div_frames
