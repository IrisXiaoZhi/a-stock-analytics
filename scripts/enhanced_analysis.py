#!/usr/bin/env python3
""""增强版分析：板块对标 + 多形态回测 + 综合研判"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from market_data import (
    tencent_quote, get_daily_bars, sina_kline, cache_kline,
    calc_ma, calc_rsi, calc_macd, calc_bollinger, calc_atr,
    scoring_card, pattern_backtest
)

# ========= 板块对标分析 =========

SECTOR_MAP = {
    "300230": {"sector": "轻工制造/橡胶塑料", "peers": ["300321", "300905", "002768", "300243"]},
    "000612": {"sector": "有色金属/铝",       "peers": ["000807", "000630", "601600", "002532"]},
    "002996": {"sector": "有色金属/再生铝",   "peers": ["002533", "000807", "000630", "601600"]},
}

def sector_comparison(code, name=""):
    """板块对标：和同行业可比公司对比"""
    info = SECTOR_MAP.get(code)
    if not info:
        return {"error": f"未知板块 {code}"}
    
    peers = info["peers"]
    all_codes = [code] + peers
    quotes = tencent_quote(all_codes)
    
    result = {
        "stock": f"{name}({code})" if name else code,
        "sector": info["sector"],
        "peers": []
    }
    
    my_data = quotes.get(code, {})
    result["price"] = my_data.get("price", 0)
    result["change_pct"] = my_data.get("change_pct", 0)
    result["pe"] = my_data.get("pe", 0)
    result["turnover"] = my_data.get("turnover", 0)
    
    # 行业排名
    peer_changes = []
    peer_pes = []
    peer_turnovers = []
    
    for p in peers:
        q = quotes.get(p, {})
        name_p = q.get("name", p)
        chg = q.get("change_pct", 0)
        pe = q.get("pe", 0)
        turn = q.get("turnover", 0)
        price_p = q.get("price", 0)
        
        entry = {"code": p, "name": name_p, "price": price_p, "change_pct": chg, "pe": pe, "turnover": turn}
        result["peers"].append(entry)
        
        peer_changes.append(chg)
        peer_pes.append(pe if pe > 0 else 999)
        peer_turnovers.append(turn)
    
    # 涨跌幅排名
    all_changes = [my_data.get("change_pct", 0)] + peer_changes
    sorted_idx = sorted(range(len(all_changes)), key=lambda i: all_changes[i], reverse=True)
    my_rank = sorted_idx.index(0) + 1  # 0 is our stock
    result["rank_in_sector"] = f"{my_rank}/{len(all_changes)}"
    result["sector_avg_change"] = round(sum(peer_changes) / len(peer_changes), 2)
    result["sector_avg_pe"] = round(sum(p for p in peer_pes if p < 999) / max(len([p for p in peer_pes if p < 999]), 1), 1)
    result["sector_avg_turnover"] = round(sum(peer_turnovers) / len(peer_turnovers), 1)
    
    # 相对强度
    rel_strength = round(my_data.get("change_pct", 0) - result["sector_avg_change"], 2)
    result["relative_strength"] = rel_strength
    result["relative_signal"] = "强势" if rel_strength > 2 else "跟随" if rel_strength > -2 else "弱势"
    
    return result


# ========= 多形态回测引擎 =========

PATTERNS = {
    "breakout_ma20":    {"name": "突破MA20",      "desc": "收盘价上穿MA20且涨幅>1%"},
    "breakout_ma60":    {"name": "突破MA60",      "desc": "收盘价上穿MA60"},
    "golden_cross":     {"name": "MACD金叉",      "desc": "MACD柱由负转正"},
    "volume_surge":     {"name": "放量突破",      "desc": "成交量>1.5倍均量+涨幅>3%"},
    "oversold_bounce":  {"name": "超跌反弹",      "desc": "RSI<30后回升"},
    "ma5_above_ma10":   {"name": "MA5上穿MA10",  "desc": "短期均线金叉"},
    "triple_bull":      {"name": "三线多头",      "desc": "MA5>MA10>MA20多头排列"},
}

def comprehensive_backtest(code, days=400):
    """多形态回测：同时跑所有模式"""
    bars = get_daily_bars(code, days)
    if len(bars) < 60:
        return {"error": f"数据不足 {len(bars)}条"}
    
    closes = [b["close"] for b in bars]
    volumes = [b["volume"] for b in bars]
    results = {}
    
    for pat_key in PATTERNS:
        signals = []
        for i in range(30, len(bars) - 5):
            window = bars[max(0, i-30):i+1]
            w_closes = [b["close"] for b in window]
            w_volumes = [b["volume"] for b in window]
            bar = bars[i]
            
            signal = False
            if pat_key == "breakout_ma20":
                ma20 = calc_ma(w_closes, 20)
                if ma20 and i > 0:
                    prev = bars[i-1]["close"]
                    if prev <= ma20 and bar["close"] > ma20 * 1.01:
                        signal = True
                        
            elif pat_key == "breakout_ma60":
                ma60 = calc_ma(w_closes, 60)
                if ma60 and i > 0:
                    prev = bars[i-1]["close"]
                    if prev <= ma60 and bar["close"] > ma60:
                        signal = True
                        
            elif pat_key == "golden_cross":
                macd = calc_macd(w_closes)
                if len(w_closes) > 26 and macd["hist"] > 0:
                    if i > 0:
                        prev_macd = calc_macd(w_closes[:-1])
                        if prev_macd["hist"] <= 0 and macd["hist"] > 0:
                            signal = True
            
            elif pat_key == "volume_surge":
                if len(w_volumes) > 20:
                    avg_vol = sum(w_volumes[-20:-1]) / 19
                    vol_ratio = bar["volume"] / avg_vol if avg_vol > 0 else 0
                    if vol_ratio > 1.5 and bar["close"] > bars[i-1]["close"] * 1.03:
                        signal = True
            
            elif pat_key == "oversold_bounce":
                rsi = calc_rsi(w_closes)
                if rsi < 35 and bar["close"] > bars[i-1]["close"]:
                    signal = True
            
            elif pat_key == "ma5_above_ma10":
                if len(w_closes) >= 10:
                    ma5 = calc_ma(w_closes, 5)
                    ma10 = calc_ma(w_closes, 10)
                    if ma5 and ma10 and ma5 > ma10:
                        prev_ma5 = calc_ma(w_closes[:-1], 5) if len(w_closes) > 5 else 0
                        prev_ma10 = calc_ma(w_closes[:-1], 10) if len(w_closes) > 10 else 0
                        if prev_ma5 and prev_ma10 and prev_ma5 <= prev_ma10:
                            signal = True
            
            elif pat_key == "triple_bull":
                if len(w_closes) >= 20:
                    ma5 = calc_ma(w_closes, 5)
                    ma10 = calc_ma(w_closes, 10)
                    ma20 = calc_ma(w_closes, 20)
                    if ma5 and ma10 and ma20 and ma5 > ma10 > ma20:
                        signal = True
            
            if signal:
                entry = bar["close"]
                future = bars[i+1:i+6]
                if len(future) >= 3:
                    exit_price = future[-1]["close"]
                    ret = (exit_price - entry) / entry * 100
                    max_dd = 0
                    for f in future:
                        dd = (f["low"] - entry) / entry * 100
                        max_dd = min(max_dd, dd)
                    signals.append({"entry": entry, "exit": exit_price, "return": ret, "max_dd": max_dd})
        
        if signals:
            wins = sum(1 for s in signals if s["return"] > 0)
            returns = [s["return"] for s in signals]
            results[pat_key] = {
                "name": PATTERNS[pat_key]["name"],
                "samples": len(signals),
                "win_rate": round(wins / len(signals) * 100, 1),
                "avg_return": round(sum(returns) / len(returns), 2),
                "max_return": round(max(returns), 2),
                "min_return": round(min(returns), 2),
                "median_return": round(sorted(returns)[len(returns)//2], 2),
                "avg_max_dd": round(sum(s["max_dd"] for s in signals) / len(signals), 2),
                "profit_factor": round(sum(r for r in returns if r > 0) / abs(sum(r for r in returns if r < 0)) if any(r < 0 for r in returns) else 999, 2),
                "best_rated": max(signals, key=lambda s: s["return"] - abs(s["max_dd"])) if signals else None,
            }
    
    # 综合研判
    summary = {"code": code, "patterns": results}
    
    best_pattern = max(results.values(), key=lambda r: r["win_rate"] * r["avg_return"]) if results else None
    if best_pattern:
        summary["best_pattern"] = best_pattern["name"]
        summary["best_pattern_win_rate"] = best_pattern["win_rate"]
        summary["best_pattern_avg_return"] = best_pattern["avg_return"]
    
    return summary


# ========= 综合研判报告 =========

def full_analysis(code, name=""):
    """输出完整的一站式分析报告"""
    lines = []
    
    # 1. 实时行情
    quotes = tencent_quote([code])
    q = quotes.get(code, {})
    price = q.get("price", 0)
    chg = q.get("change_pct", 0)
    turnover = q.get("turnover", 0)
    pe = q.get("pe", 0)
    
    lines.append("=" * 50)
    lines.append(f"📊 {name}({code}) 综合研判报告")
    lines.append("=" * 50)
    lines.append(f"现价: {price}元 ({chg:+.2f}%) 换手: {turnover}% PE: {pe}")
    lines.append("")
    
    # 2. 评分卡
    bars = get_daily_bars(code, 200)
    score = scoring_card(code, name, bars, q)
    if "error" not in score:
        lines.append("【评分卡】")
        for k in ["技术面", "资金面", "消息面", "基本面"]:
            s = score.get(k, {})
            lines.append(f"  {k}: {s.get('score', 0)}/{s.get('max', 20)}")
        lines.append(f"  总分: {score['总分']}/100  评级: {score['评级']}")
        lines.append("")
    
    # 3. 板块对标
    sec = sector_comparison(code, name)
    if "error" not in sec:
        lines.append(f"【板块对标】板块: {sec['sector']}")
        lines.append(f"  行业涨跌排名: {sec.get('rank_in_sector', 'N/A')}")
        lines.append(f"  行业平均涨跌: {sec.get('sector_avg_change', 0):.2f}%")
        lines.append(f"  相对强度: {sec.get('relative_strength', 0):+.2f}% ({sec.get('relative_signal', '')})")
        lines.append(f"  行业平均PE: {sec.get('sector_avg_pe', 0)} 自身PE: {pe}")
        lines.append(f"  行业平均换手: {sec.get('sector_avg_turnover', 0)}% 自身: {turnover}%")
        lines.append("  对标个股:")
        for p in sec.get("peers", []):
            arrow = "↑" if p.get("change_pct", 0) > 0 else "↓"
            lines.append(f"    {p['name']}({p['code']}): {p['price']}元 {arrow} {p.get('change_pct', 0):+.2f}%")
        lines.append("")
    
    # 4. 多形态回测
    bt = comprehensive_backtest(code, 400)
    if "error" not in bt:
        lines.append("【多形态回测】(5日持有)")
        patterns = bt.get("patterns", {})
        # Sort by win rate * return
        sorted_pats = sorted(patterns.values(), key=lambda p: p["win_rate"] * p["avg_return"], reverse=True)
        for p in sorted_pats:
            lines.append(f"  ◆ {p['name']}: {p['samples']}次 胜率{p['win_rate']}% 均收益{p['avg_return']}%")
        if bt.get("best_pattern"):
            lines.append(f"  最佳形态: {bt['best_pattern']} (胜率{bt['best_pattern_win_rate']}% 均收益{bt['best_pattern_avg_return']}%)")
        lines.append("")
    
    # 5. 技术指标快照
    if bars:
        closes = [b["close"] for b in bars]
        bb = calc_bollinger(closes)
        atr = calc_atr(bars)
        rsi = calc_rsi(closes)
        lines.append("【技术指标】")
        lines.append(f"  布林: 中{bb['mid']} 上{bb['upper']} 下{bb['lower']} (带宽{bb['bandwidth']:.2%})")
        lines.append(f"  ATR(14): {atr:.3f}")
        lines.append(f"  RSI(14): {rsi:.1f}")
        ma20 = calc_ma(closes, 20)
        ma60 = calc_ma(closes, 60)
        if ma20 and ma60:
            gap = (price - ma20) / ma20 * 100
            lines.append(f"  MA20: {ma20:.2f} (偏差{gap:+.1f}%)  MA60: {ma60:.2f}")
        lines.append("")
    
    # 6. 操作建议
    lines.append("【操作建议】")
    total_score = score.get("总分", 50) if "error" not in score else 50
    
    if total_score >= 70:
        stop_loss = round(price * 0.94, 2)
        target1 = round(price * 1.05, 2)
        target2 = round(price * 1.10, 2)
        lines.append("  🔴 推荐买入")
        lines.append(f"  建议区间: {round(price*0.98,2)}~{price}元")
        lines.append(f"  目标: {target1}(+5%) → {target2}(+10%)")
        lines.append(f"  止损: {stop_loss}(-6%)")
    elif total_score >= 55:
        lines.append("  🟡 观望等待")
        lines.append(f"  现价{price}元，未到最佳买点")
        lines.append(f"  关注位: {round(price*0.96,2)}元以下可考虑")
    else:
        lines.append("  🟢 回避或减仓")
        lines.append(f"  评分{total_score}，当前不宜介入")
    
    lines.append("=" * 50)
    return "\n".join(lines)


# ========= 主入口 =========

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python enhanced_analysis.py <命令> [code]")
        print("命令:")
        print("  sector <code>    板块对标分析")
        print("  backtest <code>  多形态回测")
        print("  full <code>      综合研判报告")
        print("  all              三只股票综合研判")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    STOCKS = {"300230": "永利股份", "000612": "焦作万方", "002996": "顺博合金"}
    
    if cmd == "sector":
        code = sys.argv[2] if len(sys.argv) > 2 else "300230"
        name = STOCKS.get(code, "")
        print(json.dumps(sector_comparison(code, name), ensure_ascii=False, indent=2))
    
    elif cmd == "backtest":
        code = sys.argv[2] if len(sys.argv) > 2 else "300230"
        bt = comprehensive_backtest(code)
        print(json.dumps(bt, ensure_ascii=False, indent=2, default=str))
    
    elif cmd == "full":
        code = sys.argv[2] if len(sys.argv) > 2 else "300230"
        name = STOCKS.get(code, "")
        print(full_analysis(code, name))
    
    elif cmd == "all":
        for code, name in STOCKS.items():
            print(full_analysis(code, name))
            print()
