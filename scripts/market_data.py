#!/usr/bin/env python3
"""
market_data.py — 统一数据引擎 v2.0
取代 AkShare / BaoStock，使用三大免费稳定数据源：
  - 腾讯行情 (实时) ✅ 最稳定
  - 新浪行情 (实时+K线) ✅ 次稳定
  - 同花顺行情 (实时) ✅ 备用
本地 DuckDB 缓存，减少重复请求。
"""

import json
import re
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

import urllib.request
import urllib.parse

# ── 配置 ──────────────────────────────────────────
CACHE_DB = Path(__file__).parent.parent / "data" / "market_cache.db"
REQUEST_TIMEOUT = 10

# ── 工具函数 ──────────────────────────────────────

def _ua():
    return {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def _req(url, headers=None, timeout=REQUEST_TIMEOUT):
    h = _ua()
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("gbk", errors="replace")

# ── 数据源：腾讯行情（最稳定）────────────────────

def tencent_quote(codes):
    """获取实时行情，codes = ['sz300230','sz000612','sh600519']
    返回 dict: {code: {name, price, prev_close, change, change_pct, high, low, volume, turnover, pe, ...}}
    """
    if isinstance(codes, str):
        codes = [codes]
    url = f"http://qt.gtimg.cn/q={','.join(codes)}"
    raw = _req(url)
    result = {}
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line or not line.startswith("v_"):
            continue
        parts = line.split("~")
        if len(parts) < 40:
            continue
        code = parts[2]
        try:
            d = {
                "name": parts[1],
                "code": code,
                "price": float(parts[3]) if parts[3] else 0,
                "prev_close": float(parts[4]) if parts[4] else 0,
                "open": float(parts[5]) if parts[5] else 0,
                "volume": int(parts[6]) if parts[6] else 0,
                "change": float(parts[31]) if len(parts) > 31 and parts[31] else 0,
                "change_pct": float(parts[32]) if len(parts) > 32 and parts[32] else 0,
                "high": float(parts[33]) if len(parts) > 33 and parts[33] else 0,
                "low": float(parts[34]) if len(parts) > 34 and parts[34] else 0,
                "amount": float(parts[37]) if len(parts) > 37 and parts[37] else 0,
                "turnover": float(parts[38]) if len(parts) > 38 and parts[38] else 0,
                "pe": float(parts[39]) if len(parts) > 39 and parts[39] else 0,
                "pb": float(parts[42]) if len(parts) > 42 and parts[42] else 0,
                "timestamp": parts[30] if len(parts) > 30 else "",
            }
            result[code] = d
        except (ValueError, IndexError):
            continue
    return result


# ── 数据源：新浪K线（历史日K）────────────────────

def sina_kline(code, days=120):
    """获取日K线数据
    code = 'sz300230' or '300230'
    returns list of {date, open, high, low, close, volume, pct_chg}
    """
    # Normalize code
    if code.isdigit():
        if code.startswith("6"):
            code = f"sh{code}"
        else:
            code = f"sz{code}"
    
    url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={code}&scale=240&ma=no&datalen={days}"
    try:
        raw = _req(url, headers={"Referer": "https://finance.sina.com.cn"})
        data = json.loads(raw)
        result = []
        for bar in data:
            result.append({
                "date": bar["day"],
                "open": float(bar["open"]),
                "high": float(bar["high"]),
                "low": float(bar["low"]),
                "close": float(bar["close"]),
                "volume": int(bar["volume"]),
            })
        # Calculate pct_chg
        for i in range(1, len(result)):
            prev_close = result[i-1]["close"]
            result[i]["pct_chg"] = round((result[i]["close"] - prev_close) / prev_close * 100, 2)
        if result:
            result[0]["pct_chg"] = 0
        return result
    except Exception as e:
        print(f"[WARN] 新浪K线失败 {code}: {e}")
        return []


# ── 数据源：同花顺备用实时行情 ──────────────────

def hexin_quote(code):
    """同花顺实时行情，code = 'hs_300230' / '300230'"""
    if code.isdigit():
        code = f"hs_{code}"
    url = f"http://d.10jqka.com.cn/v2/realhead/{code}/last.js"
    try:
        raw = _req(url)
        # Parse JSONP
        json_str = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_str:
            return json.loads(json_str.group())
    except:
        pass
    return {}


# ── 技术指标计算 ─────────────────────────────────

def calc_ma(prices, period):
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period

def calc_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50
    gains, losses = 0, 0
    for i in range(-period, 0):
        diff = prices[i] - prices[i-1]
        if diff > 0:
            gains += diff
        else:
            losses -= diff
    if losses == 0:
        return 100
    rs = gains / losses
    return 100 - (100 / (1 + rs))

def calc_macd(prices, fast=12, slow=26, signal=9):
    if len(prices) < slow + signal:
        return {"macd_line": 0, "signal_line": 0, "hist": 0}
    # EMA
    def ema(data, period):
        result = [data[0]]
        mult = 2 / (period + 1)
        for i in range(1, len(data)):
            result.append((data[i] - result[-1]) * mult + result[-1])
        return result
    ema_fast = ema(prices, fast)
    ema_slow = ema(prices, slow)
    macd_line = [ema_fast[i] - ema_slow[i] for i in range(len(prices))]
    signal_line = ema(macd_line, signal)
    hist = macd_line[-1] - signal_line[-1]
    return {"macd_line": round(macd_line[-1], 4), "signal_line": round(signal_line[-1], 4), "hist": round(hist, 4)}

def calc_bollinger(prices, period=20):
    if len(prices) < period:
        return {"mid": 0, "upper": 0, "lower": 0, "bandwidth": 0}
    mid = sum(prices[-period:]) / period
    variance = sum((p - mid) ** 2 for p in prices[-period:]) / period
    std = variance ** 0.5
    upper = mid + 2 * std
    lower = mid - 2 * std
    bandwidth = (upper - lower) / mid if mid else 0
    return {"mid": round(mid, 2), "upper": round(upper, 2), "lower": round(lower, 2), "bandwidth": round(bandwidth, 4)}

def calc_atr(bars, period=14):
    """bars = [{high, low, close}, ...]"""
    if len(bars) < period + 1:
        return 0
    trs = []
    for i in range(1, len(bars)):
        hl = bars[i]["high"] - bars[i]["low"]
        hc = abs(bars[i]["high"] - bars[i-1]["close"])
        lc = abs(bars[i]["low"] - bars[i-1]["close"])
        trs.append(max(hl, hc, lc))
    if not trs:
        return 0
    return sum(trs[-period:]) / period


# ── 本地缓存 ─────────────────────────────────────

def _init_cache():
    CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CACHE_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_bars (
            code TEXT, date TEXT,
            open REAL, high REAL, low REAL, close REAL, volume INTEGER, pct_chg REAL,
            PRIMARY KEY (code, date)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            code TEXT, date TEXT, data TEXT,
            PRIMARY KEY (code, date)
        )
    """)
    conn.commit()
    return conn

def cache_kline(code, bars):
    conn = _init_cache()
    for bar in bars:
        conn.execute(
            "INSERT OR REPLACE INTO daily_bars VALUES (?,?,?,?,?,?,?,?)",
            (code, bar["date"], bar["open"], bar["high"], bar["low"], bar["close"], bar["volume"], bar.get("pct_chg", 0))
        )
    conn.commit()
    conn.close()

def get_cached_kline(code, days=120):
    conn = _init_cache()
    cur = conn.execute(
        "SELECT * FROM daily_bars WHERE code=? ORDER BY date DESC LIMIT ?",
        (code, days)
    )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    conn.close()
    return list(reversed(rows))


# ── 多维度评分卡 ─────────────────────────────────

def scoring_card(code, name="", bars=None, quote=None):
    """返回 {technical, fund_flow, news_sentiment, fundamental, overall, detail}"""
    if bars is None:
        bars = get_cached_kline(code, 120)
    if not bars:
        return {"error": f"数据不足 {code}"}
    
    closes = [b["close"] for b in bars]
    latest = bars[-1]
    scores = {}
    
    # ── 技术面 (40分) ──
    tech = 0
    details = []
    
    # 均线位置
    ma5 = calc_ma(closes, 5)
    ma10 = calc_ma(closes, 10)
    ma20 = calc_ma(closes, 20)
    ma60 = calc_ma(closes, 60)
    
    price = latest["close"]
    if price > ma60: tech += 10; details.append("站上MA60 +10")
    elif price > ma20: tech += 6; details.append("站上MA20 +6")
    elif price > ma10: tech += 3; details.append("站上MA10 +3")
    else: details.append("均线下方 +0")
    
    # 均线排列
    if ma5 and ma10 and ma20:
        if ma5 > ma10 > ma20: tech += 8; details.append("多头排列 +8")
        elif ma5 < ma10 < ma20: tech += 0; details.append("空头排列 +0")
        else: tech += 4; details.append("均线交织 +4")
    
    # MACD
    macd = calc_macd(closes)
    if macd["hist"] > 0 and macd["hist"] > abs(macd.get("prev_hist", 0)):
        tech += 6; details.append("MACD金叉放量 +6")
    elif macd["hist"] > 0:
        tech += 4; details.append("MACD零轴上 +4")
    elif macd["hist"] > -0.5:
        tech += 2; details.append("MACD即将金叉 +2")
    else:
        details.append("MACD零轴下 +0")
    
    # RSI
    rsi = calc_rsi(closes)
    if 40 <= rsi <= 70: tech += 6; details.append(f"RSI{rsi:.0f}中性偏强 +6")
    elif rsi < 30: tech += 4; details.append(f"RSI{rsi:.0f}超卖反弹 +4")
    elif rsi > 80: tech += 2; details.append(f"RSI{rsi:.0f}超买 +2")
    else: tech += 3; details.append(f"RSI{rsi:.0f} +3")
    
    # 成交量
    if len(bars) > 20:
        avg_vol = sum(b["volume"] for b in bars[-20:]) / 20
        vol_ratio = latest["volume"] / avg_vol if avg_vol > 0 else 1
        if vol_ratio > 1.5: tech += 6; details.append(f"放量{vol_ratio:.1f}倍 +6")
        elif vol_ratio > 1.0: tech += 3; details.append(f"量正常{vol_ratio:.1f} +3")
        else: tech += 1; details.append(f"缩量{vol_ratio:.1f} +1")
    
    # 布林带位置
    bb = calc_bollinger(closes)
    if bb["upper"] > 0:
        pos = (price - bb["lower"]) / (bb["upper"] - bb["lower"]) if bb["upper"] != bb["lower"] else 0.5
        if 0.2 <= pos <= 0.8: tech += 4; details.append("布林中轨附近 +4")
        elif pos < 0.2: tech += 2; details.append("布林下轨 +2")
        else: tech += 1; details.append("布林上轨附近 +1")
    
    tech = min(tech, 40)
    scores["技术面"] = {"score": tech, "max": 40, "details": details}
    
    # ── 资金面 (20分) ──
    fund = 10  # Default middle score since we can't get real fund flow data
    fund_details = ["数据源限制，默认中性"]
    # Try to extract from Tencent quote if available
    if quote and quote.get("turnover", 0) > 0:
        t = quote["turnover"]
        if t > 10: fund = 16; fund_details = [f"换手{t}%活跃 +16"]
        elif t > 5: fund = 12; fund_details = [f"换手{t}%适中 +12"]
        elif t > 3: fund = 8; fund_details = [f"换手{t}%一般 +8"]
        else: fund = 6; fund_details = [f"换手{t}%偏低 +6"]
    scores["资金面"] = {"score": fund, "max": 20, "details": fund_details}
    
    # ── 消息面 (20分) ──
    # 从涨幅反推市场关注度
    news = 10
    pct = latest.get("pct_chg", 0) or 0
    news_details = []
    if abs(pct) > 5:
        news = 14; news_details = [f"涨幅{pct}%关注度高 +14"]
    elif abs(pct) > 3:
        news = 12; news_details = [f"涨幅{pct}%有热度 +12"]
    elif abs(pct) > 1:
        news = 10; news_details = ["正常波动 +10"]
    else:
        news = 8; news_details = ["平淡 +8"]
    scores["消息面"] = {"score": news, "max": 20, "details": news_details}
    
    # ── 基本面 (20分) ──
    fundamental = 10
    funda_details = ["估值面数据需财报补充，暂给中性"]
    # PE估值判断
    if quote and quote.get("pe", 0) > 0:
        pe = quote["pe"]
        if pe < 15: fundamental = 16; funda_details = [f"PE{pe}偏低 +16"]
        elif pe < 30: fundamental = 13; funda_details = [f"PE{pe}合理 +13"]
        elif pe < 50: fundamental = 10; funda_details = [f"PE{pe}偏高 +10"]
        else: fundamental = 6; funda_details = [f"PE{pe}高估 +6"]
    scores["基本面"] = {"score": fundamental, "max": 20, "details": funda_details}
    
    total = tech + fund + news + fundamental
    scores["总分"] = total
    scores["评级"] = "A" if total >= 80 else "B" if total >= 65 else "C" if total >= 50 else "D"
    
    return scores


# ── 历史形态回测胜率 ────────────────────────────

def pattern_backtest(code, lookback_days=120, pattern_type="breakout_ma20"):
    """
    简单回测：过去出现类似信号后，未来5天涨跌概率
    返回: {win_rate, avg_return, max_drawdown, samples}
    """
    bars = get_cached_kline(code, lookback_days)
    if len(bars) < 60:
        return {"error": f"数据不足, 当前{len(bars)}条"}
    
    results = []
    for i in range(20, len(bars) - 5):
        window = bars[max(0, i-20):i+1]
        closes = [b["close"] for b in window]
        prices = [b["close"] for b in window]
        
        signal = False
        if pattern_type == "breakout_ma20":
            ma20 = calc_ma(closes, 20)
            if ma20 and len(window) > 1:
                prev_close = window[-2]["close"]
                if prev_close <= ma20 and window[-1]["close"] > ma20 * 1.01:
                    signal = True
        elif pattern_type == "macd_golden_cross":
            macd = calc_macd(closes)
            if len(closes) > 26 and macd["hist"] > 0 and macd["hist"] < 0.2:
                signal = True
        
        if signal:
            entry = window[-1]["close"]
            future = bars[i+1:i+6]
            if len(future) >= 3:
                exit_price = future[-1]["close"]
                ret = (exit_price - entry) / entry * 100
                max_drawdown = 0
                for f in future:
                    dd = (f["low"] - entry) / entry * 100
                    max_drawdown = min(max_drawdown, dd)
                results.append({"entry": entry, "exit": exit_price, "return": ret, "max_dd": max_drawdown})
    
    if not results:
        return {"samples": 0, "win_rate": 0, "avg_return": 0, "error": "无匹配信号"}
    
    wins = sum(1 for r in results if r["return"] > 0)
    return {
        "samples": len(results),
        "win_rate": round(wins / len(results) * 100, 1),
        "avg_return": round(sum(r["return"] for r in results) / len(results), 2),
        "max_drawdown_avg": round(sum(r["max_dd"] for r in results) / len(results), 2),
        "best_return": round(max(r["return"] for r in results), 2),
        "worst_return": round(min(r["return"] for r in results), 2),
    }


# ── 日线数据获取（带缓存）────────────────────────

def get_daily_bars(code, days=120, force_refresh=False):
    """获取日K线，优先缓存，没有则从Sina拉取"""
    cached = get_cached_kline(code, days)
    if len(cached) >= days and not force_refresh:
        return cached
    
    # Fetch from Sina
    bars = sina_kline(code, days)
    if bars:
        cache_kline(code, bars)
        return bars
    # Fall back to cached even if insufficient
    return cached if cached else []


# ── 主入口 ──────────────────────────────────────

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python market_data.py <命令> [参数]")
        print("命令:")
        print("  quote <code>        实时行情")
        print("  kline <code> [days]  K线数据")
        print("  score <code>        评分卡")
        print("  backtest <code>     回测")
        print("  sector <code>       板块对标")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "quote":
        codes = sys.argv[2:]
        if not codes:
            codes = ["sz300230", "sz000612", "sz002996"]
        result = tencent_quote(codes)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    
    elif cmd == "kline":
        code = sys.argv[2] if len(sys.argv) > 2 else "300230"
        days = int(sys.argv[3]) if len(sys.argv) > 3 else 120
        bars = get_daily_bars(code, days)
        print(json.dumps(bars, ensure_ascii=False, indent=2))
    
    elif cmd == "score":
        code = sys.argv[2] if len(sys.argv) > 2 else "300230"
        name = sys.argv[3] if len(sys.argv) > 3 else ""
        bars = get_daily_bars(code, 120)
        quote = tencent_quote([code])
        result = scoring_card(code, name, bars, quote.get(code))
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    
    elif cmd == "backtest":
        code = sys.argv[2] if len(sys.argv) > 2 else "300230"
        pattern = sys.argv[3] if len(sys.argv) > 3 else "breakout_ma20"
        bars = get_daily_bars(code, 120)
        result = pattern_backtest(code, 120, pattern)
        print(json.dumps(result, ensure_ascii=False, indent=2))
