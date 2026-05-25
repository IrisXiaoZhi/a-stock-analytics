from __future__ import annotations

"""A-share extended research tools: fund flow, limit-up, dragon-tiger,
market sentiment, sector rotation, macro, unlock calendar, block trades,
and intraday alerts."""

import argparse
import json
import math
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("A_STOCK_DATA_DIR", ROOT / "data"))

os.environ.setdefault("NO_PROXY", "*")
os.environ.setdefault("no_proxy", "*")


def _load_ak():
    import akshare as ak
    return ak


def _norm(code: str) -> str:
    d = re.sub(r"\D", "", code)
    if len(d) != 6:
        raise SystemExit(f"invalid code: {code}")
    return d


def _out(obj: Any) -> None:
    def _d(o: Any) -> Any:
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
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=_d))


def _dft(df: pd.DataFrame, limit: int = 50) -> list[dict]:
    return df.fillna("").head(limit).to_dict(orient="records")


# ── 1. 资金流向 ──────────────────────────────────────────

def fund_flow_individual(stock: str | None = None) -> dict:
    ak = _load_ak()
    try:
        df = ak.stock_individual_fund_flow_rank(indicator="今日")
    except Exception:
        df = ak.stock_individual_fund_flow(stock="沪深两市", market="全部")
    if stock:
        code = _norm(stock)
        df = df[df["代码"].astype(str).str.contains(code)]
    cols = ["代码","名称","最新价","涨跌幅","今日主力净流入-净额","今日主力净流入-净占比","今日超大单净流入-净额","今日大单净流入-净额","今日中单净流入-净额","今日小单净流入-净额"]
    available = [c for c in cols if c in df.columns]
    return {"kind":"individual_fund_flow","count":len(df),"data":_dft(df[available],100)}

def fund_flow_sector() -> dict:
    ak = _load_ak()
    try:
        df = ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流")
    except Exception:
        df = ak.stock_sector_fund_flow_rank(indicator="今日")
    return {"kind":"sector_fund_flow","count":len(df),"data":_dft(df,60)}

def fund_flow_north() -> dict:
    ak = _load_ak()
    try:
        df = ak.stock_hsgt_hist_em(symbol="北向资金")
        df = df.sort_values("日期").tail(60)
        return {"kind":"north_bound","count":len(df),"data":_dft(df,60)}
    except Exception:
        # Try alternative
        df = ak.stock_hsgt_north_net_flow_in_em(symbol="北上")
        return {"kind":"north_bound_alt","count":len(df),"data":_dft(df,60)}

# ── 2. 涨停板分析 ──────────────────────────────────────

def limit_up(today: str | None = None) -> dict:
    if today is None:
        today = datetime.now().strftime("%Y%m%d")
    ak = _load_ak()
    result: dict[str, Any] = {"date": today}

    # Main limit-up pool
    try:
        df = ak.stock_zt_pool_em(date=today)
        df = df.sort_values("连板数", ascending=False) if "连板数" in df.columns else df
        result["limit_up"] = {"count": len(df), "data": _dft(df, 100)}
    except Exception as e:
        result["limit_up"] = {"error": str(e)}

    # Strong / consecutive
    try:
        df2 = ak.stock_zt_pool_strong_em(date=today)
        result["strong"] = {"count": len(df2), "data": _dft(df2, 50)}
    except Exception as e:
        result["strong"] = {"error": str(e)}

    # 炸板(limit-up then fail)
    try:
        df3 = ak.stock_zt_pool_zbgc_em(date=today)
        result["busted"] = {"count": len(df3), "data": _dft(df3, 50)}
    except Exception as e:
        result["busted"] = {"error": str(e)}

    return result

# ── 3. 龙虎榜 ────────────────────────────────────────────

def dragon_tiger(date: str | None = None) -> dict:
    if date is None:
        date = datetime.now().strftime("%Y%m%d")
    ak = _load_ak()
    result: dict[str, Any] = {"date": date}
    try:
        # Detail: per-stock per-branch
        df = ak.stock_lhb_detail_em()
        if not df.empty:
            # Column name may vary between akshare versions
            date_col = "上榜日期" if "上榜日期" in df.columns else df.columns[0]
            df_detail = df.sort_values(date_col, ascending=False) if date_col in df.columns else df
            result["detail_count"] = len(df_detail)
            result["details"] = _dft(df_detail, 100)
    except Exception as e:
        result["details"] = {"error": str(e)}
    try:
        # Stock statistics: consolidated per stock
        df2 = ak.stock_lhb_stock_statistic_em()
        if not df2.empty:
            result["stocks"] = _dft(df2, 50)
    except Exception as e:
        result["stocks"] = {"error": str(e)}
    try:
        # Branch statistics: top securities branches
        df3 = ak.stock_lhb_hyyyb_em()
        if not df3.empty:
            result["branches"] = _dft(df3, 30)
    except Exception as e:
        result["branches"] = {"error": str(e)}
    return result

def sentiment_and_alerts_spot() -> pd.DataFrame | None:
    """Fetch spot data with retry. Returns DataFrame or None."""
    import time
    for attempt in range(3):
        try:
            if attempt > 0:
                time.sleep(2 * attempt)  # Exponential backoff
            ak = _load_ak()
            return ak.stock_zh_a_spot_em()
        except Exception:
            if attempt == 2:
                return None
    return None


# ── 4. 市场情绪 ────────────────────────────────────────────

def market_sentiment() -> dict:
    ak = _load_ak()
    result: dict[str, Any] = {"ts": datetime.now().isoformat()}

    # Full market spot to count advances / declines / limit-up / limit-down
    spot = sentiment_and_alerts_spot()
    if spot is not None:
        result["total_stocks"] = len(spot)
        if "涨跌幅" in spot.columns:
            pct = pd.to_numeric(spot["涨跌幅"], errors="coerce")
            result["advance"] = int((pct > 0).sum())
            result["decline"] = int((pct < 0).sum())
            result["flat"] = int((pct == 0).sum())
            result["up_ratio"] = round(result["advance"] / max(result["advance"] + result["decline"], 1), 4)
            # Average gain/loss
            gains = pct[pct > 0]
            losses = pct[pct < 0]
            result["avg_gain"] = round(float(gains.mean()), 2) if len(gains) else None
            result["avg_loss"] = round(float(losses.mean()), 2) if len(losses) else None
            # Limit-up & limit-down count
            result["limit_up_count"] = int((pct >= 9.9).sum())
            result["limit_down_count"] = int((pct <= -9.9).sum())
        if "成交额" in spot.columns:
            amt = pd.to_numeric(spot["成交额"], errors="coerce")
            result["total_amount_bn"] = round(float(amt.sum()) / 1e8, 2)
    else:
        result["spot_error"] = "spot data unavailable (rate limited)"

    # Index snapshot
    try:
        indices = ["上证指数", "深证成指", "创业板指", "科创50"]
        index_data = {}
        for idx in indices:
            try:
                name_map = {"上证指数": "sh000001", "深证成指": "sz399001", "创业板指": "sz399006", "科创50": "sh000688"}
                code = name_map.get(idx, idx)
                df = ak.stock_zh_index_daily(symbol=code)
                if not df.empty:
                    last = df.iloc[-1]
                    index_data[idx] = {
                        "close": float(last["close"]) if "close" in last else None,
                        "pct_chg": float(last.get("pct_chg", 0)) if pd.notna(last.get("pct_chg")) else None,
                        "volume": float(last.get("volume", 0)) if pd.notna(last.get("volume")) else None,
                    }
            except Exception:
                pass
        result["indices"] = index_data
    except Exception as e:
        result["indices_error"] = str(e)

    return result

# ── 5. 板块轮动 ────────────────────────────────────────────

def sector_rotation(days: int = 5) -> dict:
    """Sector rotation analysis using fund-flow ranking as primary signal.
    Fund flow into sectors is a leading indicator for sector rotation."""
    ak = _load_ak()
    result: dict[str, Any] = {"days": days, "note": "sector ranking by fund flow (资金流向驱动的板块轮动)"}

    # Use fund flow sector ranking (works reliably, single API call)
    try:
        df = ak.stock_sector_fund_flow_rank(indicator=f"{days}日" if days > 1 else "今日", sector_type="行业资金流")
        if not df.empty:
            # Extract sector name and net flow
            for col in ["名称", "板块名称", "行业名称"]:
                if col in df.columns:
                    break
            else:
                col = df.columns[0]
            flow_col = None
            for fc in ["主力净流入-净额", "主力净流入", "净流入"]:
                if fc in df.columns:
                    flow_col = fc
                    break
            rankings = []
            for _, row in df.head(20).iterrows():
                name = str(row[col])
                flow = float(row[flow_col]) if flow_col and pd.notna(row.get(flow_col)) else 0
                rankings.append({"sector": name, "net_flow_wan": round(flow / 1e4, 0) if abs(flow) > 1e4 else round(flow, 0)})
            result["rankings"] = rankings
            result["top_3"] = rankings[:3]
            result["bottom_3"] = rankings[-3:] if len(rankings) >= 3 else rankings
            return result
    except Exception as e:
        result["fund_flow_error"] = str(e)

    # Fallback: try a few key sector histories
    key_sectors = ["半导体", "银行", "证券", "白酒", "电力"]
    perf: list[dict] = []
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=days + 5)).strftime("%Y%m%d")
    for name in key_sectors:
        try:
            import time
            time.sleep(0.5)  # Rate limit protection
            df = ak.stock_board_industry_hist_em(symbol=name, period="日k", start_date=start, end_date=end, adjust="")
            if df.empty or "收盘" not in df.columns:
                continue
            closes = pd.to_numeric(df["收盘"], errors="coerce").dropna()
            if len(closes) < 2:
                continue
            ret = float((closes.iloc[-1] / closes.iloc[0] - 1) * 100)
            perf.append({"sector": name, f"ret_{days}d_pct": round(ret, 2)})
        except Exception:
            continue
    perf.sort(key=lambda x: x[f"ret_{days}d_pct"], reverse=True)
    result["rankings"] = perf
    result["top_3"] = perf[:3]
    result["bottom_3"] = perf[-3:] if len(perf) >= 3 else perf
    return result

# ── 6. 宏观数据 ────────────────────────────────────────────

def macro_data(indicator: str = "all") -> dict:
    ak = _load_ak()
    result: dict[str, Any] = {}

    indicators = ["pmi", "cpi", "m2", "social_finance"] if indicator == "all" else [indicator]

    for ind in indicators:
        try:
            if ind == "pmi":
                df = ak.macro_china_pmi()
                # Data is already sorted latest-first
                df.columns = [c.lower() for c in df.columns]
                result["pmi"] = _dft(df.head(12), 12)
            elif ind == "cpi":
                df = ak.macro_china_cpi_monthly()
                result["cpi"] = _dft(df.head(12), 12)
            elif ind == "m2":
                df = ak.macro_china_money_supply()
                result["m2"] = _dft(df.head(12), 12)
            elif ind == "social_finance":
                df = ak.macro_china_shrzgm()
                result["social_finance"] = _dft(df.head(12), 12)
        except Exception as e:
            result[ind] = {"error": str(e)}

    return result

# ── 7. 限售解禁 ────────────────────────────────────────────

def unlock_calendar(date: str | None = None, code: str | None = None) -> dict:
    if date is None:
        date = datetime.now().strftime("%Y%m%d")
    ak = _load_ak()
    # API uses start_date/end_date range, not a single date
    start = (datetime.strptime(date, "%Y%m%d") - timedelta(days=7)).strftime("%Y%m%d")
    end = (datetime.strptime(date, "%Y%m%d") + timedelta(days=30)).strftime("%Y%m%d")
    try:
        df = ak.stock_restricted_release_detail_em(start_date=start, end_date=end)
        if code:
            c = _norm(code)
            col = "股票代码" if "股票代码" in df.columns else df.columns[0]
            df = df[df[col].astype(str).str.contains(c)]
        # Sort by market cap impact if column exists
        for cap_col in ["实际解禁市值", "解禁市值"]:
            if cap_col in df.columns:
                df[cap_col] = pd.to_numeric(df[cap_col], errors="coerce")
                df = df.sort_values(cap_col, ascending=False)
                break
        return {"date": date, "range": f"{start}-{end}", "count": len(df), "data": _dft(df, 50)}
    except Exception as e:
        return {"error": str(e)}

# ── 8. 大宗交易 ────────────────────────────────────────────

def block_trade(code: str | None = None, days: int = 5) -> dict:
    ak = _load_ak()
    start = (datetime.now() - timedelta(days=max(days * 2, 10))).strftime("%Y%m%d")
    end = datetime.now().strftime("%Y%m%d")
    result: dict[str, Any] = {"code": code, "days": days}
    try:
        # API symbol choices: 'A股', 'B股', '基金', '债券'
        # For individual stock filtering, query all A stocks then filter
        df = ak.stock_dzjy_mrmx(symbol="A股", start_date=start, end_date=end)
        if code:
            c = _norm(code)
            col = "证券代码" if "证券代码" in df.columns else df.columns[0]
            df = df[df[col].astype(str).str.contains(c)]
        if df.empty:
            return {"code": code, "days": days, "message": "no block trades found"}
        if "交易日期" in df.columns:
            df = df.sort_values("交易日期", ascending=False)
        # calculate discount/premium stats
        if "折溢价比率" in df.columns:
            df["折溢价比率"] = pd.to_numeric(df["折溢价比率"], errors="coerce")
        if "成交额" in df.columns:
            df["成交额"] = pd.to_numeric(df["成交额"], errors="coerce")
        return {"code": code, "days": days, "count": len(df), "data": _dft(df, 100)}
    except Exception as e:
        return {"error": str(e)}

# ── 9. 盘中异动监控 ──────────────────────────────────────

def intraday_alerts(code: str | None = None) -> dict:
    """Check for abnormal conditions using recent daily data."""
    result: dict[str, Any] = {"ts": datetime.now().isoformat(), "alerts": []}

    spot = sentiment_and_alerts_spot()
    if spot is None:
        result["error"] = "spot data unavailable (rate limited)"
        result["data_time"] = datetime.now().strftime("%H:%M")
        return result

    try:

        # Top volume-ratio stocks (量比 > 3)
        if "量比" in spot.columns:
            vol_ratio = pd.to_numeric(spot["量比"], errors="coerce")
            high_vol = spot[vol_ratio > 3].copy()
            if not high_vol.empty:
                high_vol = high_vol.sort_values("量比", ascending=False)
                result["alerts"].append({
                    "type": "high_volume_ratio",
                    "desc": "量比>3的个股",
                    "count": len(high_vol),
                    "top": _dft(high_vol.head(20), 20)
                })

        # Top gainers & losers
        if "涨跌幅" in spot.columns:
            pct = pd.to_numeric(spot["涨跌幅"], errors="coerce")
            spot_pct = spot.copy()
            spot_pct["涨跌幅_num"] = pct
            gainers = spot_pct[spot_pct["涨跌幅_num"] > 5].sort_values("涨跌幅_num", ascending=False)
            losers = spot_pct[spot_pct["涨跌幅_num"] < -5].sort_values("涨跌幅_num")
            if not gainers.empty:
                result["alerts"].append({
                    "type": "big_gainers",
                    "desc": "涨幅>5%的个股",
                    "count": len(gainers),
                    "top": _dft(gainers.head(20), 20)
                })
            if not losers.empty:
                result["alerts"].append({
                    "type": "big_losers",
                    "desc": "跌幅>5%的个股",
                    "count": len(losers),
                    "top": _dft(losers.head(20), 20)
                })

        # Turnover rate anomaly (>15%)
        if "换手率" in spot.columns:
            turnover = pd.to_numeric(spot["换手率"], errors="coerce")
            high_turn = spot[turnover > 15].copy()
            if not high_turn.empty:
                high_turn = high_turn.sort_values("换手率", ascending=False)
                result["alerts"].append({
                    "type": "high_turnover",
                    "desc": "换手率>15%的个股（异常活跃）",
                    "count": len(high_turn),
                    "top": _dft(high_turn.head(20), 20)
                })

        if code:
            c = _norm(code)
            row = spot[spot["代码"].astype(str) == c]
            if not row.empty:
                r = row.iloc[0].to_dict()
                result["stock"] = {
                    "code": c,
                    "name": r.get("名称"),
                    "price": r.get("最新价"),
                    "pct_chg": r.get("涨跌幅"),
                    "vol_ratio": r.get("量比"),
                    "turnover": r.get("换手率"),
                    "amount": r.get("成交额"),
                }

        result["data_time"] = datetime.now().strftime("%H:%M")
    except Exception as e:
        result["error"] = str(e)

    return result

# ── CLI ──────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="A-share extended tools for OpenClaw")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # 1. Fund flow
    p = sub.add_parser("fund-flow")
    p.add_argument("--type", default="individual", choices=["individual","sector","north"])
    p.add_argument("--stock")

    # 2. Limit-up
    p = sub.add_parser("limit-up")
    p.add_argument("--date")

    # 3. Dragon-tiger
    p = sub.add_parser("dragon-tiger")
    p.add_argument("--date")

    # 4. Market sentiment
    sub.add_parser("sentiment")

    # 5. Sector rotation
    p = sub.add_parser("sector-rotation")
    p.add_argument("--days", type=int, default=5)

    # 6. Macro
    p = sub.add_parser("macro")
    p.add_argument("--indicator", default="all", choices=["all","pmi","cpi","m2","social_finance"])

    # 7. Unlock calendar
    p = sub.add_parser("unlock")
    p.add_argument("--date")
    p.add_argument("--stock")

    # 8. Block trade
    p = sub.add_parser("block-trade")
    p.add_argument("--stock")
    p.add_argument("--days", type=int, default=5)

    # 9. Intraday alerts
    p = sub.add_parser("alerts")
    p.add_argument("--stock")

    args = parser.parse_args()

    if args.cmd == "fund-flow":
        if args.type == "sector":
            _out(fund_flow_sector())
        elif args.type == "north":
            _out(fund_flow_north())
        else:
            _out(fund_flow_individual(args.stock))
    elif args.cmd == "limit-up":
        _out(limit_up(args.date))
    elif args.cmd == "dragon-tiger":
        _out(dragon_tiger(args.date))
    elif args.cmd == "sentiment":
        _out(market_sentiment())
    elif args.cmd == "sector-rotation":
        _out(sector_rotation(args.days))
    elif args.cmd == "macro":
        _out(macro_data(args.indicator))
    elif args.cmd == "unlock":
        _out(unlock_calendar(args.date, args.stock))
    elif args.cmd == "block-trade":
        _out(block_trade(args.stock, args.days))
    elif args.cmd == "alerts":
        _out(intraday_alerts(args.stock))


if __name__ == "__main__":
    main()
