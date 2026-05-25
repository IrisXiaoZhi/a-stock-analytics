#!/usr/bin/env python3
"""收盘总结 + Git提交"""
import json, os, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from market_data import tencent_quote, get_daily_bars, scoring_card, pattern_backtest

CODES = {"300230": "永利股份", "000612": "焦作万方", "002996": "顺博合金"}
REPO_DIR = Path(__file__).parent.parent

import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace') if hasattr(sys.stdout, 'reconfigure') else None

def main():
    today = "2026-05-25"
    quotes = tencent_quote(list(CODES.keys()))
    
    lines = []
    lines.append(f"# 📊 收盘报告 {today}\n")
    
    for code, name in CODES.items():
        q = quotes.get(code, {})
        bars = get_daily_bars(code, 200)
        score = scoring_card(code, name, bars, q)
        bt = pattern_backtest(code, 200, "breakout_ma20")
        
        price = q.get("price", 0)
        chg = q.get("change_pct", 0)
        turnover = q.get("turnover", 0)
        pe = q.get("pe", 0)
        
        lines.append(f"## ◆ {name}({code})")
        lines.append(f"收盘: {price}元 ({chg:+.2f}%) | 换手: {turnover}% | PE: {pe}")
        
        if "error" not in score:
            lines.append(f"总分: {score['总分']}/100 评级: {score['评级']}")
            for k in ["技术面", "资金面", "消息面", "基本面"]:
                s = score.get(k, {})
                lines.append(f"  {k}: {s.get('score', 0)}/{s.get('max', 20)}")
        else:
            lines.append(f"评分: {score['error']}")
        
        if "error" not in bt:
            lines.append(f"回测(突破MA20): {bt['samples']}次信号 | 胜率{bt['win_rate']}% | 均收益{bt['avg_return']}%")
        else:
            lines.append(f"回测: {bt.get('error', '')}")
        lines.append("")
    
    # 操作建议
    lines.append("## 📋 操作建议")
    for code, name in CODES.items():
        q = quotes.get(code, {})
        price = q.get("price", 0)
        chg = q.get("change_pct", 0)
        score = scoring_card(code, name, get_daily_bars(code, 200), q)
        total = score.get("总分", 0)
        rating = score.get("评级", "D")
        
        if total >= 70:
            lines.append(f"🔴 {name}({code}) — 评分{total}({rating}) 建议关注买入")
        elif total >= 55:
            lines.append(f"🟡 {name}({code}) — 评分{total}({rating}) 观望")
        else:
            lines.append(f"🟢 {name}({code}) — 评分{total}({rating}) 回避")

    report = "\n".join(lines)
    print(report)
    
    # 保存到文件
    report_path = REPO_DIR / "data" / f"收盘报告_{today}.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n已保存: {report_path}")
    
    # 保存收盘快照JSON
    snapshot_path = REPO_DIR / "data" / f"snapshot_{today}.json"
    snapshot = {"date": today, "quotes": {}}
    for code, name in CODES.items():
        q = quotes.get(code, {})
        snapshot["quotes"][code] = {
            "name": name,
            "price": q.get("price"),
            "change_pct": q.get("change_pct"),
            "turnover": q.get("turnover"),
            "pe": q.get("pe"),
        }
    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    print(f"已保存: {snapshot_path}")
    
    # Git提交
    try:
        subprocess.run(["git", "add", "."], cwd=REPO_DIR, capture_output=True)
        subprocess.run(["git", "commit", "-m", f"📝 收盘报告 {today}"], cwd=REPO_DIR, capture_output=True)
        result = subprocess.run(["git", "push"], cwd=REPO_DIR, capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ Git 推送成功")
        else:
            print(f"⚠️ Git 推送: {result.stderr[:200]}")
    except Exception as e:
        print(f"⚠️ Git: {e}")

if __name__ == "__main__":
    main()
