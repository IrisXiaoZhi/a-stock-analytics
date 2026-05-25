#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小龙虾每日涨停潜力股扫描器
每日收盘后运行，扫描全市场选出2只最有涨停潜力的股票
选股逻辑：量价齐升 + 底部放量启动 + 板块热点 + 技术形态突破
"""
import sys, json, os, re
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# 设置控制台编码，避免GBK报错
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')

def get_today_str():
    return datetime.now().strftime('%Y-%m-%d')

def is_trading_day():
    return datetime.now().weekday() < 5

def fetch_daily_top():
    """获取今日涨幅榜数据 - 使用腾讯API（更稳定）"""
    try:
        import urllib.request
        import json as _json
        # 获取沪深所有A股数据
        # 东方财富实时行情接口
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = (
            "?pn=1&pz=5000&po=1&np=1&fltt=2&invt=2&"
            "fid=f3&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048&"
            "fields=f12,f14,f2,f3,f15,f16,f17,f18"
        )
        req = urllib.request.Request(url + params, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://quote.eastmoney.com/"
        })
        resp = urllib.request.urlopen(req, timeout=15)
        text = resp.read().decode('utf-8')
        data = _json.loads(text)
        items = data.get('data', {}).get('diff', [])
        
        rows = []
        for item in items:
            code = str(item.get('f12', '')).zfill(6)
            name = item.get('f14', '')
            price = item.get('f2', 0)
            pct = item.get('f3', 0)
            high = item.get('f15', 0)
            low = item.get('f16', 0)
            amount = item.get('f18', 0) or 0
            turnover = item.get('f17', 0) or 0
            
            if price is None or pct is None:
                continue
            price = float(price)
            pct = float(pct)
            if price <= 0:
                continue
            if pct <= 0 or pct > 9.5:  # 排除已涨停的
                continue
            if pct < 3:
                continue
            
            rows.append({
                '代码': code,
                '名称': name,
                '最新价': price,
                '涨跌幅': pct,
                '最高': high,
                '最低': low,
                '成交额': amount,
                '换手率': turnover
            })
        
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        df = df.sort_values('涨跌幅', ascending=False)
        return df
    except Exception as e:
        print(f"[ERROR] fetch_daily_top: {e}", file=sys.stderr)
        return pd.DataFrame()

# 热门板块关键词（老板要的风口）
HOT_SECTOR_KEYWORDS = [
    '半导体', '芯片', 'AI', '算力', '机器人', '人形机器人',
    '光模块', 'CPO', 'PCB', '存储', '封测',
    '算力', '大模型', '数据', '国产软件',
    '消费电子', '智能', '激光', '量子',
    '低空经济', '飞行汽车', '航天', '军工电子',
    '新能源车', '智能驾驶', '汽车电子'
]

# 冷门行业关键词（排除！）
COLD_SECTOR_KEYWORDS = [
    '钢铁', '煤炭', '水泥', '地产', '房地产',
    '银行', '保险', '券商', '白酒', '食品',
    '纺织', '服装', '造纸', '农业', '养殖',
    '石油', '化工', '有色', '金属', '建材'
]


def _is_hot_sector(name):
    """判断是否属于热门风口板块"""
    for kw in HOT_SECTOR_KEYWORDS:
        if kw in name:
            return True
    return False


def _is_cold_sector(name):
    """判断是否属于冷门传统板块"""
    for kw in COLD_SECTOR_KEYWORDS:
        if kw in name:
            return True
    return False


def filter_quality_candidates(df):
    """精选质量好的候选股 - 匹配老板快枪策略"""
    if df.empty:
        return pd.DataFrame()

    candidates = []
    for _, row in df.iterrows():
        score = 0
        code = str(row.get('代码', '')).zfill(6)
        name = str(row.get('名称', ''))
        pct = float(row.get('涨跌幅', 0))
        price = float(row.get('最新价', 0))
        turnover = float(row.get('换手率', 0) or 0)
        amount = float(row.get('成交额', 0) or 0) / 1e8

        # 排除ST/退市
        if 'ST' in name or '退' in name or 'S' in name:
            continue

        # 排除冷门传统行业（扣分项）
        if _is_cold_sector(name):
            continue  # 冷门股直接排除

        # 风口加分
        if _is_hot_sector(name):
            score += 3  # 风口股大加分

        # 价格适中
        if 3 < price < 25:
            score += 1

        # 涨幅3-8%，没涨停才有D2空间
        if 3 <= pct <= 8:
            score += 2

        # 换手率5-15%，活跃但不过热
        if 5 <= turnover <= 15:
            score += 2
        elif 3 <= turnover < 5:
            score += 1

        # 成交额>1亿，有资金
        if amount > 1:
            score += 1
            if amount > 5:
                score += 1
            if amount > 10:
                score += 1  # 大资金猛干

        candidates.append({
            'code': code,
            'name': name,
            'price': price,
            'pct': pct,
            'turnover': turnover,
            'amount': amount,
            'score': score,
            'is_hot': _is_hot_sector(name)
        })

    result = pd.DataFrame(candidates)
    if not result.empty:
        result = result.sort_values('score', ascending=False)
    return result

def analyze_candidate_deep(code, name, price):
    """对候选股做深度技术分析"""
    try:
        import baostock as bs
        bs.login()

        if code.startswith(('00', '30')):
            adj_code = f"sz.{code}"
        else:
            adj_code = f"sh.{code}"

        start = (datetime.now() - timedelta(days=120)).strftime('%Y-%m-%d')
        end = get_today_str()
        rs = bs.query_history_k_data_plus(
            adj_code, "date,open,high,low,close,volume,amount",
            start_date=start, end_date=end,
            frequency="d", adjustflag="2"
        )

        data = []
        while rs.next():
            d = dict(zip(rs.fields, rs.get_row_data()))
            data.append(d)
        bs.logout()

        if len(data) < 20:
            return None

        df = pd.DataFrame(data)
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        close = df['close'].values.astype(float)
        volume = df['volume'].values.astype(float)

        ma5 = np.mean(close[-5:]) if len(close) >= 5 else close[-1]
        ma20 = np.mean(close[-20:]) if len(close) >= 20 else close[-1]
        ma60 = np.mean(close[-60:]) if len(close) >= 60 else close[-1]
        vol_ma5 = np.mean(volume[-5:]) if len(volume) >= 5 else volume[-1]

        last_close = close[-1]
        vol_ratio = volume[-1] / vol_ma5 if vol_ma5 > 0 else 1
        trend_up = bool(last_close > ma5 > ma20 > ma60)
        trend_just_start = bool(last_close > ma5 and ma5 > ma20 and last_close > ma20)

        recent_low = np.min(close[-20:])
        rebound_pct = (last_close / recent_low - 1) * 100
        recent_high = np.max(close[-60:]) if len(close) >= 60 else np.max(close)
        dist_to_high = (recent_high / last_close - 1) * 100

        result = {
            'price': round(float(last_close), 2),
            'ma5': round(float(ma5), 2),
            'ma20': round(float(ma20), 2),
            'ma60': round(float(ma60), 2),
            'vol_ratio': round(float(vol_ratio), 2),
            'trend_up': trend_up,
            'trend_just_start': trend_just_start,
            'rebound_pct': round(float(rebound_pct), 1),
            'dist_to_high': round(float(dist_to_high), 1),
            'near_low': round(float(recent_low), 2),
            'near_high_60d': round(float(recent_high), 2),
        }

        score_deep = 0
        if trend_up:
            score_deep += 3
        if trend_just_start:
            score_deep += 2
        if vol_ratio > 1.5:
            score_deep += 2
        if 5 < rebound_pct < 30:
            score_deep += 1
        if dist_to_high < 15:
            score_deep += 2
        result['score_deep'] = score_deep

        return result
    except Exception as e:
        print(f"[ERROR] analyze_deep {code}: {e}", file=sys.stderr)
        return None

def run_scan():
    """主扫描流程"""
    if not is_trading_day():
        out = {"status": "not_trading_day", "date": get_today_str()}
        print(json.dumps(out, ensure_ascii=False))
        return

    print(json.dumps({"step": "scan_start", "date": get_today_str()}, ensure_ascii=False))

    df = fetch_daily_top()
    if df.empty or len(df) == 0:
        print(json.dumps({"status": "no_data", "date": get_today_str()}, ensure_ascii=False))
        return

    candidates = filter_quality_candidates(df)
    if candidates.empty:
        print(json.dumps({"status": "no_candidates", "date": get_today_str()}, ensure_ascii=False))
        return

    top_candidates = candidates.head(10)

    deep_results = []
    for _, c in top_candidates.head(5).iterrows():
        tech = analyze_candidate_deep(c['code'], c['name'], c['price'])
        if tech:
            entry = c.to_dict()
            entry['tech'] = tech
            deep_results.append(entry)

    if not deep_results:
        print(json.dumps({"status": "no_deep_results", "date": get_today_str()}, ensure_ascii=False))
        return

    for r in deep_results:
        r['final_score'] = r['score'] + r['tech']['score_deep']

    deep_results.sort(key=lambda x: x['final_score'], reverse=True)
    picks = deep_results[:2]

    result = {
        "status": "ok",
        "date": get_today_str(),
        "picks": []
    }

    for i, pick in enumerate(picks):
        t = pick['tech']
        entry_reason = []
        if t['trend_up']:
            entry_reason.append("多头排列")
        if t['vol_ratio'] > 1.5:
            entry_reason.append("放量上攻")
        if t['dist_to_high'] < 10:
            entry_reason.append(f"即将突破前高({t['near_high_60d']}元)")
        if pick['score'] >= 4:
            entry_reason.append("活跃资金关注")

        pick_info = {
            "rank": i + 1,
            "code": pick['code'],
            "name": pick['name'],
            "price": t['price'],
            "pct": pick['pct'],
            "turnover": pick['turnover'],
            "reasons": entry_reason,
            "ma5": t['ma5'],
            "ma20": t['ma20'],
            "ma60": t['ma60'],
            "vol_ratio": t['vol_ratio'],
            "dist_to_high": t['dist_to_high'],
            "support": t['ma20'],
            "target_1": round(t['price'] * 1.05, 2),
            "target_2": round(t['price'] * 1.10, 2),
            "stop_loss": round(min(t['ma20'], t['price'] * 0.97), 2),
        }
        result["picks"].append(pick_info)

    # 保存结果
    os.makedirs(DATA_DIR, exist_ok=True)
    out_path = os.path.join(DATA_DIR, f"daily_picks_{get_today_str()}.json")
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 输出JSON结果供调用者解析
    print(json.dumps(result, ensure_ascii=False, default=str))

if __name__ == "__main__":
    run_scan()
