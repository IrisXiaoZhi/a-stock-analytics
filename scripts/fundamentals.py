#!/usr/bin/env python3
"""基本面深度分析 - 金融博士级评估"""
import baostock as bs
import json, sys
from datetime import datetime, timedelta

def deep_analysis(code):
    """金融博士级基本面分析"""
    bs.login()
    result = {}
    
    # === 利润质量 ===
    rs = bs.query_profit_data(code, year=2025, quarter=1)
    if rs.next():
        p = dict(zip(rs.fields, rs.get_row_data()))
        net_profit = float(p.get('netProfit',0) or 0)
        rev = float(p.get('MBRevenue',0) or 0)
        result['profit_quality'] = {
            'net_profit_wan': net_profit/1e4,
            'revenue_wan': rev/1e4,
            'np_margin': float(p.get('npMargin',0) or 0)*100,
            'gp_margin': float(p.get('gpMargin',0) or 0)*100,
            'roe': float(p.get('roeAvg',0) or 0)*100,
            'eps_ttm': float(p.get('epsTTM',0) or 0)
        }
    
    # === 安全边际 ===
    rs = bs.query_balance_data(code, year=2025, quarter=1)
    if rs.next():
        b = dict(zip(rs.fields, rs.get_row_data()))
        result['safety'] = {
            'current_ratio': float(b.get('currentRatio',0) or 0),
            'quick_ratio': float(b.get('quickRatio',0) or 0),
            'cash_ratio': float(b.get('cashRatio',0) or 0),
            'asset_liability_ratio': float(b.get('liabilityToAsset',0) or 0)*100,
            'equity_multiplier': float(b.get('assetToEquity',0) or 0)
        }
    
    # === 成长性 ===
    rs = bs.query_growth_data(code, year=2025, quarter=1)
    if rs.next():
        g = dict(zip(rs.fields, rs.get_row_data()))
        result['growth'] = {
            'yoy_equity': float(g.get('YOYEquity',0) or 0)*100,
            'yoy_netprofit': float(g.get('YOYNetProfit',0) or 0)*100,
            'yoy_revenue': float(g.get('YOYMiniProfit',0) or 0)*100,
            'yoy_eps': float(g.get('YOEEPS',0) or 0)*100
        }
    
    # === 现金流质量 ===
    rs = bs.query_cash_flow_data(code, year=2025, quarter=1)
    if rs.next():
        c = dict(zip(rs.fields, rs.get_row_data()))
        result['cashflow'] = {
            'cash_ratio_sales': float(c.get('Catexpsales',0) or 0)*100,
            'ocf_to_revenue': float(c.get('OCFToRevenue',0) or 0)*100,
            'ocf': float(c.get('OCF',0) or 0)/1e4
        }
    
    bs.logout()
    return result

def value_analysis(code, current_price):
    """估值分析"""
    fin = deep_analysis(code)
    result = {'price': current_price, 'valuation': {}}
    
    if 'profit_quality' in fin:
        eps = fin['profit_quality'].get('eps_ttm', 0)
        if eps > 0:
            pe = current_price / eps
            result['valuation']['pe_ttm'] = round(pe, 2)
            result['valuation']['pe_level'] = '低估' if pe < 20 else ('合理' if pe < 40 else '偏高' if pe < 60 else '高估')
    
    if 'safety' in fin:
        eq = fin['safety'].get('equity_multiplier', 0)
        roe = fin.get('profit_quality', {}).get('roe', 0)
        if eq > 0 and roe > 0:
            pb = pe * roe / 100 if 'pe_ttm' in result.get('valuation',{}) else 0
            result['valuation']['pb'] = round(pb, 2) if pb > 0 else 'N/A'
    
    result['finance'] = fin
    return result

if __name__ == '__main__':
    code = sys.argv[1] if len(sys.argv) > 1 else 'sz.000725'
    price = float(sys.argv[2]) if len(sys.argv) > 2 else 0
    if price > 0:
        _out = lambda d: print(json.dumps(d, ensure_ascii=False, indent=2))
        _out(value_analysis(code, price))
    else:
        _out = lambda d: print(json.dumps(d, ensure_ascii=False, indent=2))
        _out(deep_analysis(code))
