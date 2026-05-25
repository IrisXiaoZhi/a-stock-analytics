from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import math
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("A_STOCK_DATA_DIR", ROOT / "data"))
REPORT_DIR = Path(os.environ.get("A_STOCK_REPORT_DIR", ROOT / "reports"))
WATCHLIST_DIR = ROOT / "watchlists"
DB_PATH = DATA_DIR / "a_stock.duckdb"

# Some Windows setups expose a system proxy that is fine for browsers but breaks
# public market data endpoints used by AkShare. Default to direct connections.
os.environ.setdefault("NO_PROXY", "*")
os.environ.setdefault("no_proxy", "*")


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    WATCHLIST_DIR.mkdir(parents=True, exist_ok=True)


def norm_code(code: str) -> str:
    digits = re.sub(r"\D", "", code)
    if len(digits) != 6:
        raise SystemExit(f"stock code must contain 6 digits: {code}")
    return digits


def market_prefix(code: str) -> str:
    code = norm_code(code)
    if code.startswith(("6", "9")):
        return f"sh{code}"
    return f"sz{code}"


def baostock_code(code: str) -> str:
    code = norm_code(code)
    if code.startswith(("6", "9")):
        return f"sh.{code}"
    return f"sz.{code}"


def cn_symbol(code: str) -> str:
    return norm_code(code)


def to_json(obj: Any) -> None:
    def default(o: Any) -> Any:
        if isinstance(o, (pd.Timestamp, datetime)):
            return o.isoformat()
        if isinstance(o, Path):
            return str(o)
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            if math.isnan(float(o)):
                return None
            return float(o)
        if pd.isna(o):
            return None
        return str(o)

    print(json.dumps(obj, ensure_ascii=False, indent=2, default=default))


def load_akshare():
    try:
        import akshare as ak
    except Exception as exc:
        raise SystemExit(f"akshare is not available: {exc}") from exc
    return ak


def history_df(code: str, days: int = 250, adjust: str = "qfq") -> pd.DataFrame:
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=max(days * 2, 60))).strftime("%Y%m%d")
    try:
        ak = load_akshare()
        df = ak.stock_zh_a_hist(symbol=cn_symbol(code), period="daily", start_date=start, end_date=end, adjust=adjust)
    except Exception as primary_exc:
        df = history_df_baostock(code, days=days, adjust=adjust, primary_exc=primary_exc)
    if df.empty:
        raise SystemExit(f"no history returned for {code}")
    rename = {
        "日期": "date",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
        "成交额": "amount",
        "振幅": "amplitude",
        "涨跌幅": "pct_chg",
        "涨跌额": "change",
        "换手率": "turnover",
    }
    df = df.rename(columns=rename)
    df["date"] = pd.to_datetime(df["date"])
    for col in ["open", "close", "high", "low", "volume", "amount", "pct_chg", "turnover"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["code"] = norm_code(code)
    df = df.sort_values("date").tail(days).reset_index(drop=True)
    cache_history(df)
    return df


def history_df_baostock(code: str, days: int, adjust: str, primary_exc: Exception | None = None) -> pd.DataFrame:
    try:
        import baostock as bs
    except Exception as exc:
        raise SystemExit(f"AkShare failed ({primary_exc}); BaoStock is not available: {exc}") from exc
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=max(days * 2, 60))).strftime("%Y-%m-%d")
    adjustflag = {"hfq": "1", "qfq": "2", "": "3"}.get(adjust, "2")
    with contextlib.redirect_stdout(io.StringIO()):
        login = bs.login()
    try:
        if login.error_code != "0":
            raise SystemExit(f"BaoStock login failed: {login.error_msg}; AkShare failed: {primary_exc}")
        fields = "date,open,high,low,close,volume,amount,pctChg,turn"
        rs = bs.query_history_k_data_plus(
            baostock_code(code),
            fields,
            start_date=start,
            end_date=end,
            frequency="d",
            adjustflag=adjustflag,
        )
        if rs.error_code != "0":
            raise SystemExit(f"BaoStock query failed: {rs.error_msg}; AkShare failed: {primary_exc}")
        rows: list[list[str]] = []
        while rs.next():
            rows.append(rs.get_row_data())
        df = pd.DataFrame(rows, columns=fields.split(","))
    finally:
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                bs.logout()
        except Exception:
            pass
    if df.empty:
        return df
    df = df.rename(
        columns={
            "date": "date",
            "pctChg": "pct_chg",
            "turn": "turnover",
        }
    )
    df["date"] = pd.to_datetime(df["date"])
    for col in ["open", "close", "high", "low", "volume", "amount", "pct_chg", "turnover"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["code"] = norm_code(code)
    return df.sort_values("date").tail(days).reset_index(drop=True)


def cache_history(df: pd.DataFrame) -> None:
    ensure_dirs()
    with duckdb.connect(str(DB_PATH)) as con:
        con.execute(
            """
            create table if not exists daily_history (
              code varchar,
              date timestamp,
              open double,
              close double,
              high double,
              low double,
              volume double,
              amount double,
              pct_chg double,
              turnover double,
              primary key(code, date)
            )
            """
        )
        cols = [c for c in ["code", "date", "open", "close", "high", "low", "volume", "amount", "pct_chg", "turnover"] if c in df.columns]
        con.register("incoming", df[cols])
        con.execute("delete from daily_history using incoming where daily_history.code = incoming.code and daily_history.date = incoming.date")
        con.execute(f"insert into daily_history select {', '.join(cols)} from incoming")


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    close = out["close"]
    for n in [5, 10, 20, 60, 120, 250]:
        out[f"ma{n}"] = close.rolling(n).mean()
    out["vol_ma5"] = out["volume"].rolling(5).mean()
    out["vol_ma20"] = out["volume"].rolling(20).mean()
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    out["macd_dif"] = ema12 - ema26
    out["macd_dea"] = out["macd_dif"].ewm(span=9, adjust=False).mean()
    out["macd_hist"] = (out["macd_dif"] - out["macd_dea"]) * 2
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    out["rsi14"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    out["boll_mid"] = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    out["boll_up"] = out["boll_mid"] + 2 * std20
    out["boll_low"] = out["boll_mid"] - 2 * std20
    return out


def summarize_indicators(code: str, days: int) -> dict[str, Any]:
    df = compute_indicators(history_df(code, days=days))
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last
    close = float(last["close"])
    levels = {k: float(last[k]) for k in ["ma5", "ma10", "ma20", "ma60", "ma120", "ma250"] if pd.notna(last.get(k))}
    trend = []
    if "ma20" in levels and close >= levels["ma20"]:
        trend.append("close_above_ma20")
    if "ma60" in levels and close >= levels["ma60"]:
        trend.append("close_above_ma60")
    if pd.notna(last.get("vol_ma20")) and last["volume"] > last["vol_ma20"] * 1.5:
        trend.append("volume_expansion")
    if pd.notna(last.get("macd_hist")) and pd.notna(prev.get("macd_hist")) and last["macd_hist"] > prev["macd_hist"]:
        trend.append("macd_hist_improving")
    support = min([v for v in levels.values() if v <= close], default=None)
    resistance = min([v for v in levels.values() if v > close], default=None)
    return {
        "code": norm_code(code),
        "date": last["date"],
        "close": close,
        "pct_chg": float(last["pct_chg"]) if pd.notna(last.get("pct_chg")) else None,
        "levels": levels,
        "signals": trend,
        "nearest_ma_support": support,
        "nearest_ma_resistance": resistance,
        "rsi14": float(last["rsi14"]) if pd.notna(last.get("rsi14")) else None,
        "macd_hist": float(last["macd_hist"]) if pd.notna(last.get("macd_hist")) else None,
    }


def risk_scan(code: str) -> dict[str, Any]:
    ak = load_akshare()
    result: dict[str, Any] = {"code": norm_code(code), "checks": [], "data_source": "akshare/public"}
    try:
        spot = ak.stock_zh_a_spot_em()
        row = spot[spot["代码"].astype(str) == norm_code(code)]
        if not row.empty:
            r = row.iloc[0].to_dict()
            result["name"] = r.get("名称")
            result["latest"] = r.get("最新价")
            result["pct_chg"] = r.get("涨跌幅")
            name = str(r.get("名称", ""))
            if "ST" in name.upper():
                result["checks"].append({"level": "high", "item": "ST flag", "detail": name})
            if pd.to_numeric(pd.Series([r.get("量比")]), errors="coerce").iloc[0] >= 3:
                result["checks"].append({"level": "medium", "item": "volume ratio elevated", "detail": r.get("量比")})
    except Exception as exc:
        result["checks"].append({"level": "unknown", "item": "spot_fetch_failed", "detail": str(exc)})
    try:
        ind = summarize_indicators(code, days=260)
        result["technical"] = ind
        close = ind["close"]
        ma250 = ind["levels"].get("ma250")
        ma60 = ind["levels"].get("ma60")
        if ma250 and close < ma250:
            result["checks"].append({"level": "medium", "item": "below_ma250", "detail": f"close {close:.2f} < ma250 {ma250:.2f}"})
        if ma60 and close < ma60:
            result["checks"].append({"level": "medium", "item": "below_ma60", "detail": f"close {close:.2f} < ma60 {ma60:.2f}"})
    except Exception as exc:
        result["checks"].append({"level": "unknown", "item": "technical_fetch_failed", "detail": str(exc)})
    if not result["checks"]:
        result["checks"].append({"level": "ok", "item": "no_basic_red_flags_from_available_public_data", "detail": "still verify announcements and financials"})
    return result


def backtest_ma(code: str, fast: int, slow: int, days: int) -> dict[str, Any]:
    if fast >= slow:
        raise SystemExit("--fast must be smaller than --slow")
    df = history_df(code, days=days)
    df = compute_indicators(df)
    df["fast"] = df["close"].rolling(fast).mean()
    df["slow"] = df["close"].rolling(slow).mean()
    df["signal"] = (df["fast"] > df["slow"]).astype(int)
    df["position"] = df["signal"].shift(1).fillna(0)
    df["ret"] = df["close"].pct_change().fillna(0)
    df["strategy_ret"] = df["position"] * df["ret"]
    trades = int((df["signal"].diff().abs() > 0).sum())
    equity = (1 + df["strategy_ret"]).cumprod()
    buyhold = (1 + df["ret"]).cumprod()
    drawdown = equity / equity.cummax() - 1
    return {
        "code": norm_code(code),
        "fast": fast,
        "slow": slow,
        "start": df["date"].iloc[0],
        "end": df["date"].iloc[-1],
        "strategy_return": float(equity.iloc[-1] - 1),
        "buy_hold_return": float(buyhold.iloc[-1] - 1),
        "max_drawdown": float(drawdown.min()),
        "trade_count_signal_changes": trades,
        "last_signal": "hold" if int(df["signal"].iloc[-1]) == 1 else "cash",
    }


def watchlist_path(name: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_\-\u4e00-\u9fff]+", "-", name).strip("-") or "default"
    return WATCHLIST_DIR / f"{safe}.csv"


def add_watch(name: str, code: str, label: str | None) -> dict[str, Any]:
    ensure_dirs()
    path = watchlist_path(name)
    rows = []
    if path.exists():
        rows = list(csv.DictReader(path.open("r", encoding="utf-8-sig")))
    code = norm_code(code)
    rows = [r for r in rows if r.get("code") != code]
    rows.append({"code": code, "label": label or "", "added_at": datetime.now().isoformat(timespec="seconds")})
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["code", "label", "added_at"])
        writer.writeheader()
        writer.writerows(rows)
    return {"watchlist": name, "path": str(path), "count": len(rows)}


def scan_watch(name: str) -> dict[str, Any]:
    path = watchlist_path(name)
    if not path.exists():
        raise SystemExit(f"watchlist not found: {path}")
    rows = list(csv.DictReader(path.open("r", encoding="utf-8-sig")))
    results = []
    for row in rows:
        code = row["code"]
        try:
            item = summarize_indicators(code, days=260)
            item["label"] = row.get("label")
        except Exception as exc:
            item = {"code": code, "label": row.get("label"), "error": str(exc)}
        results.append(item)
    return {"watchlist": name, "count": len(results), "results": results}


def journal_add(code: str, side: str, qty: float, price: float, reason: str) -> dict[str, Any]:
    ensure_dirs()
    path = DATA_DIR / "trading_journal.csv"
    exists = path.exists()
    row = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "code": norm_code(code),
        "side": side,
        "qty": qty,
        "price": price,
        "amount": qty * price,
        "reason": reason,
    }
    with path.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not exists:
            writer.writeheader()
        writer.writerow(row)
    return {"journal": str(path), "added": row}


def journal_list(limit: int) -> dict[str, Any]:
    path = DATA_DIR / "trading_journal.csv"
    if not path.exists():
        return {"journal": str(path), "entries": []}
    rows = list(csv.DictReader(path.open("r", encoding="utf-8-sig")))
    return {"journal": str(path), "entries": rows[-limit:]}


def main() -> None:
    ensure_dirs()
    parser = argparse.ArgumentParser(description="A-share research helper for OpenClaw")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("history")
    p.add_argument("code")
    p.add_argument("--days", type=int, default=120)
    p.add_argument("--adjust", default="qfq", choices=["", "qfq", "hfq"])

    p = sub.add_parser("indicators")
    p.add_argument("code")
    p.add_argument("--days", type=int, default=260)

    p = sub.add_parser("risk")
    p.add_argument("code")

    p = sub.add_parser("backtest-ma")
    p.add_argument("code")
    p.add_argument("--fast", type=int, default=20)
    p.add_argument("--slow", type=int, default=60)
    p.add_argument("--days", type=int, default=900)

    p = sub.add_parser("watchlist-add")
    p.add_argument("name")
    p.add_argument("code")
    p.add_argument("label", nargs="?")

    p = sub.add_parser("watchlist-scan")
    p.add_argument("name")

    p = sub.add_parser("journal-add")
    p.add_argument("code")
    p.add_argument("side", choices=["buy", "sell", "plan", "observe"])
    p.add_argument("qty", type=float)
    p.add_argument("price", type=float)
    p.add_argument("--reason", default="")

    p = sub.add_parser("journal-list")
    p.add_argument("--limit", type=int, default=20)

    args = parser.parse_args()
    if args.cmd == "history":
        df = history_df(args.code, args.days, args.adjust)
        to_json({"code": norm_code(args.code), "rows": len(df), "latest": df.tail(5).to_dict(orient="records")})
    elif args.cmd == "indicators":
        to_json(summarize_indicators(args.code, args.days))
    elif args.cmd == "risk":
        to_json(risk_scan(args.code))
    elif args.cmd == "backtest-ma":
        to_json(backtest_ma(args.code, args.fast, args.slow, args.days))
    elif args.cmd == "watchlist-add":
        to_json(add_watch(args.name, args.code, args.label))
    elif args.cmd == "watchlist-scan":
        to_json(scan_watch(args.name))
    elif args.cmd == "journal-add":
        to_json(journal_add(args.code, args.side, args.qty, args.price, args.reason))
    elif args.cmd == "journal-list":
        to_json(journal_list(args.limit))


if __name__ == "__main__":
    main()
