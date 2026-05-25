#!/usr/bin/env python3
"""Tushare Pro tool for OpenClaw - handles rate limiting"""
import tushare as ts
import json, sys, time
from datetime import datetime, timedelta

TOKEN = '07a21cbd898de0cd91499384e2593e31a0b32d0c7c825d9f456b3ebd'
ts.set_token(TOKEN)
pro = ts.pro_api()

# Rate limit tracking
_last_call = {}

def _rate_limit(api_name, min_interval=65):
    """Ensure minimum interval between calls"""
    now = time.time()
    if api_name in _last_call:
        elapsed = now - _last_call[api_name]
        if elapsed < min_interval:
            wait = min_interval - elapsed
            time.sleep(wait)
    _last_call[api_name] = time.time()

def _out(data):
    print(json.dumps(data, ensure_ascii=False, default=str))

def fund_flow(stock_codes, date='20260522'):
    """Get fund flow data for stocks"""
    results = []
    for code in stock_codes:
        _rate_limit('moneyflow')
        try:
            df = pro.moneyflow(ts_code=code, start_date=date, end_date=date)
            if df is not None and not df.empty:
                r = df.iloc[0]
                results.append({
                    "code": code,
                    "net_mf_amt": float(r.get('net_mf_amt',0) or 0),
                    "buy_lg_amt": float(r.get('buy_lg_amt',0) or 0),
                    "sell_lg_amt": float(r.get('sell_lg_amt',0) or 0),
                    "buy_elg_amt": float(r.get('buy_elg_amt',0) or 0),
                    "sell_elg_amt": float(r.get('sell_elg_amt',0) or 0),
                    "buy_mid_amt": float(r.get('buy_mid_amt',0) or 0),
                    "sell_mid_amt": float(r.get('sell_mid_amt',0) or 0),
                })
        except Exception as e:
            if '频率超限' in str(e):
                _last_call.pop('moneyflow', None)
                time.sleep(5)
                continue
            results.append({"code": code, "error": str(e)[:60]})
    _out(results)

def dragon_tiger(trade_date='20260522'):
    """Get dragon-tiger board data"""
    _rate_limit('top_list')
    try:
        df = pro.top_list(trade_date=trade_date)
        if df is not None and not df.empty:
            data = df.to_dict('records')
            _out(data[:20])
        else:
            _out({"msg": "no data"})
    except Exception as e:
        _out({"error": str(e)[:60]})

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'help'
    if cmd == 'fund':
        codes = sys.argv[2].split(',') if len(sys.argv) > 2 else ['000725.SZ']
        date = sys.argv[3] if len(sys.argv) > 3 else datetime.now().strftime('%Y%m%d')
        fund_flow(codes, date)
    elif cmd == 'dragon':
        date = sys.argv[2] if len(sys.argv) > 2 else '20260522'
        dragon_tiger(date)
    else:
        print("Usage:")
        print("  fund <codes> [date]       - 资金流向, codes逗号分隔")
        print("  dragon [date]              - 龙虎榜")
        print("  Example:")
        print("  fund 000725.SZ,300230.SZ")
        print("  dragon 20260522")
