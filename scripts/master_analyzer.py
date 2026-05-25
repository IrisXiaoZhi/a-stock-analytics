#!/usr/bin/env python3
"""
🐲 小龙虾全能股票分析器 v1.0
数据源: BaoStock + Tushare + Sina/Tencent + Tavily + 技术分析
"""
import sys, json, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def _out(data):
    print(json.dumps(data, ensure_ascii=False, default=str, indent=2))

# ===== 模块1: BaoStock 财务数据 =====
def baostock_finance(code):
    import baostock as bs
    bs.login()
    result = {}
    # 利润表
    rs = bs.query_profit_data(code, year=2025, quarter=1)
    if rs.next():
        p = dict(zip(rs.fields, rs.get_row_data()))
        result['profit'] = {
            'roe': float(p.get('roeAvg',0) or 0)*100,
            'np_margin': float(p.get('npMargin',0) or 0)*100,
            'net_profit': float(p.get('netProfit',0) or 0)/1e8,
            'eps': float(p.get('epsTTM',0) or 0)
        }
    # 资产负债表
    rs = bs.query_balance_data(code, year=2025, quarter=1)
    if rs.next():
        b = dict(zip(rs.fields, rs.get_row_data()))
        result['balance'] = {
            'current_ratio': float(b.get('currentRatio',0) or 0),
            'debt_ratio': float(b.get('liabilityToAsset',0) or 0)*100
        }
    # 杜邦
    rs = bs.query_dupont_data(code, year=2025, quarter=1)
    if rs.next():
        d = dict(zip(rs.fields, rs.get_row_data()))
        result['dupont'] = {
            'roe': float(d.get('dupontROE',0) or 0)*100,
            'leverage': float(d.get('dupontAssetStoEquity',0) or 0),
            'turnover': float(d.get('dupontAssetTurn',0) or 0)
        }
    bs.logout()
    return result

# ===== 模块2: 技术分析 =====
def technical_analysis(code, days=120):
    import baostock as bs
    import pandas as pd
    import numpy as np
    from datetime import datetime, timedelta
    
    bs.login()
    end = datetime.now()
    start = end - timedelta(days=days*2)
    rs = bs.query_history_k_data_plus(
        code, "date,open,high,low,close,volume,amount,turn,pctChg",
        start_date=start.strftime("%Y-%m-%d"),
        end_date=end.strftime("%Y-%m-%d"),
        frequency="d", adjustflag="2")
    
    rows = []
    while rs.next():
        rows.append(rs.get_row_data())
    bs.logout()
    
    if len(rows) < 20:
        return {"error": "数据不足"}
    
    df = pd.DataFrame(rows[-days:], columns=['date','open','high','low','close','volume','amount','turn','pctChg'])
    for c in ['open','high','low','close','volume','amount','turn','pctChg']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    
    result = {}
    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    vol = df['volume'].values
    
    # 均线
    for ma in [5, 10, 20, 60]:
        if len(close) >= ma:
            result[f'MA{ma}'] = round(np.mean(close[-ma:]), 2)
    
    # 均线多头/空头排列
    if len(close) >= 20:
        ma5 = np.mean(close[-5:])
        ma10 = np.mean(close[-10:])
        ma20 = np.mean(close[-20:])
        result['ma_trend'] = '多头排列' if ma5 > ma10 > ma20 else ('空头排列' if ma5 < ma10 < ma20 else '交叉')
    
    # MACD
    if len(close) >= 26:
        ema12 = pd.Series(close).ewm(span=12).mean().values
        ema26 = pd.Series(close).ewm(span=26).mean().values
        dif = ema12 - ema26
        dea = pd.Series(dif).ewm(span=9).mean().values
        macd = 2 * (dif - dea)
        result['macd'] = {
            'dif': round(float(dif[-1]), 4),
            'dea': round(float(dea[-1]), 4),
            'macd': round(float(macd[-1]), 4),
            'trend': '金叉' if dif[-1] > dea[-1] and dif[-2] <= dea[-2] else (
                     '死叉' if dif[-1] < dea[-1] and dif[-2] >= dea[-2] else (
                     '多头' if dif[-1] > dea[-1] else '空头'))
        }
    
    # RSI
    if len(close) >= 14:
        delta = pd.Series(close).diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs_val = gain / loss
        rsi = 100 - (100 / (1 + rs_val))
        result['rsi14'] = round(float(rsi.iloc[-1]), 1)
        result['rsi_status'] = '超买' if rsi.iloc[-1] > 70 else ('超卖' if rsi.iloc[-1] < 30 else '正常')
    
    # 布林带
    if len(close) >= 20:
        ma20_val = np.mean(close[-20:])
        std20 = np.std(close[-20:])
        result['boll'] = {
            'mid': round(ma20_val, 2),
            'upper': round(ma20_val + 2*std20, 2),
            'lower': round(ma20_val - 2*std20, 2),
            'bandwidth': round(4*std20/ma20_val*100, 2)
        }
    
    # 量价分析
    vol_ma5 = np.mean(vol[-5:]) if len(vol) >= 5 else 0
    vol_ma20 = np.mean(vol[-20:]) if len(vol) >= 20 else 0
    result['volume'] = {
        'vol_ratio': round(vol_ma5/vol_ma20, 2) if vol_ma20 > 0 else 0,
        'vol_trend': '放量' if vol_ma5 > vol_ma20*1.2 else ('缩量' if vol_ma5 < vol_ma20*0.8 else '正常')
    }
    
    return result

# ===== 模块3: 综合评分 =====
def score_stock(code, name, price):
    tech = technical_analysis(code, 60)
    fin = baostock_finance(code)
    
    score = 0
    reasons = []
    risks = []
    
    # 技术评分
    rsi = tech.get('rsi14', 50)
    if rsi and rsi < 30:
        score += 15; reasons.append('RSI超卖反弹')
    elif rsi and 30 <= rsi <= 50:
        score += 10; reasons.append('RSI低位')
    
    bb = tech.get('boll', {})
    if bb.get('bandwidth', 0) < 6:
        score += 15; reasons.append(f"布林带宽{bb['bandwidth']}% 弹簧收紧")
    
    if tech.get('macd', {}).get('trend') == '金叉':
        score += 10; reasons.append('MACD金叉')
    
    vol = tech.get('volume', {})
    if vol.get('vol_ratio', 0) > 1.2:
        score += 10; reasons.append('温和放量')
    
    # 基本面评分
    p = fin.get('profit', {})
    if p.get('roe', 0) > 5:
        score += 10; reasons.append(f"ROE{p['roe']:.1f}%")
    if p.get('np_margin', 0) > 10:
        score += 10; reasons.append(f"净利率{p['np_margin']:.1f}%")
    
    b = fin.get('balance', {})
    if b.get('debt_ratio', 100) < 50:
        score += 5; reasons.append('低负债')
    
    return {
        "code": code, "name": name, "price": price,
        "score": score, "max_score": 75,
        "reasons": reasons, "risks": risks,
        "tech": tech,
        "finance": fin
    }

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'help'
    if cmd == 'score':
        code = sys.argv[2]; name = sys.argv[3]; price = float(sys.argv[4]) if len(sys.argv) > 4 else 0
        _out(score_stock(code, name, price))
    elif cmd == 'tech':
        code = sys.argv[2]
        tech = technical_analysis(code)
        _out(tech)
    elif cmd == 'full':
        code = sys.argv[2]; name = sys.argv[3] if len(sys.argv) > 3 else ''
        price = float(sys.argv[4]) if len(sys.argv) > 4 else 0
        result = score_stock(code, name, price)
        _out(result)
    else:
        print("用法:")
        print("  full <code> [name] [price]  - 完整分析")
        print("  tech <code>                 - 技术分析")
        print("  score <code> <name> <price> - 综合评分")
