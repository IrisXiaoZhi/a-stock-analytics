#!/usr/bin/env python3
"""BaoStock A-share data tool - Financial, K-line, Industry data"""
import baostock as bs
from datetime import datetime, timedelta
import json
import sys

def _out(data):
    print(json.dumps(data, ensure_ascii=False, default=str))

def kline(code, days=60, adjust="qfq"):
    """Get daily K-line. adjust: qfq=前复权, hfq=后复权, none=不复权"""
    adj_map = {"qfq": "2", "hfq": "1", "none": "3"}
    bs.login()
    end = datetime.now()
    start = end - timedelta(days=days*2)
    rs = bs.query_history_k_data_plus(
        code, "date,open,high,low,close,volume,amount,turn,pctChg",
        start_date=start.strftime("%Y-%m-%d"),
        end_date=end.strftime("%Y-%m-%d"),
        frequency="d", adjustflag=adj_map.get(adjust, "2"))
    data = []
    while rs.next():
        data.append(rs.get_row_data())
    bs.logout()
    return data[-days:] if len(data) > days else data

def finance(code, year=2025, quarter=1):
    """Get comprehensive financial data"""
    bs.login()
    result = {"code": code, "year": year, "quarter": quarter}
    
    # 利润表 (Profit)
    rs = bs.query_profit_data(code, year=year, quarter=quarter)
    if rs.next():
        result["profit"] = dict(zip(rs.fields, rs.get_row_data()))
    
    # 资产负债表 (Balance Sheet)
    rs = bs.query_balance_data(code, year=year, quarter=quarter)
    if rs.next():
        result["balance"] = dict(zip(rs.fields, rs.get_row_data()))
    
    # 现金流 (Cash Flow)
    rs = bs.query_cash_flow_data(code, year=year, quarter=quarter)
    if rs.next():
        result["cashflow"] = dict(zip(rs.fields, rs.get_row_data()))
    
    # 运营数据 (Operation)
    rs = bs.query_operation_data(code, year=year, quarter=quarter)
    if rs.next():
        result["operation"] = dict(zip(rs.fields, rs.get_row_data()))
    
    # 成长性 (Growth)
    rs = bs.query_growth_data(code, year=year, quarter=quarter)
    if rs.next():
        result["growth"] = dict(zip(rs.fields, rs.get_row_data()))
    
    # 杜邦 (Dupont)
    rs = bs.query_dupont_data(code, year=year, quarter=quarter)
    if rs.next():
        result["dupont"] = dict(zip(rs.fields, rs.get_row_data()))
    
    bs.logout()
    return result

def stock_basic(code):
    """Get basic stock info"""
    bs.login()
    rs = bs.query_stock_basic(code)
    data = []
    while rs.next():
        data.append(dict(zip(rs.fields, rs.get_row_data())))
    bs.logout()
    return data

def industry():
    """Get industry classification"""
    bs.login()
    rs = bs.query_stock_industry()
    data = {}
    while rs.next():
        r = rs.get_row_data()
        data[r[1]] = {"name": r[2], "industry": r[3]}
    bs.logout()
    return data

def test():
    """Test run on our top picks"""
    picks = {
        "sz.000725": "京东方A",
        "sz.300230": "永利股份",
        "sz.000612": "焦作万方",
        "sz.002996": "顺博合金",
        "sz.000532": "华金资本",
        "sh.600888": "新疆众和",
    }
    
    for code, name in picks.items():
        print(f"\n{'='*50}")
        print(f"📊 {code} {name}")
        
        # Recent K-line
        data = kline(code, 10, "qfq")
        if data:
            print(f"  最近5天收盘: ", end="")
            for d in data[-5:]:
                print(f"{d[0][-5:]}={d[4]}", end=" ")
            last_chg = float(data[-1][8]) if data[-1][8] else 0
            print(f"  最后涨幅: {last_chg:+.2f}%")
        
        # Financial snapshot
        fin = finance(code, 2025, 1)
        if "profit" in fin:
            p = fin["profit"]
            roe = float(p.get("roeAvg", 0) or 0) * 100
            np = float(p.get("netProfit", 0) or 0) / 1e8  # to 亿
            margin = float(p.get("npMargin", 0) or 0) * 100
            eps = float(p.get("epsTTM", 0) or 0)
            print(f"  ROE={roe:.2f}%  净利润={np:.1f}亿  净利率={margin:.2f}%  EPS={eps:.2f}")
        
        if "dupont" in fin:
            d = fin["dupont"]
            print(f"  杜邦ROE={float(d.get('dupontROE',0) or 0)*100:.2f}% 杠杆={float(d.get('dupontAssetStoEquity',0) or 0):.2f}")
        
        if "balance" in fin:
            b = fin["balance"]
            cr = float(b.get("currentRatio", 0) or 0)
            dr = float(b.get("liabilityToAsset", 0) or 0) * 100
            print(f"  流动比率={cr:.2f}  资产负债率={dr:.2f}%")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    
    if cmd == "kline":
        code = sys.argv[2]
        days = int(sys.argv[3]) if len(sys.argv) > 3 else 30
        _out(kline(code, days, sys.argv[4] if len(sys.argv) > 4 else "qfq"))
    elif cmd == "finance":
        code = sys.argv[2] if len(sys.argv) > 2 else "sz.000725"
        year = int(sys.argv[3]) if len(sys.argv) > 3 else 2025
        q = int(sys.argv[4]) if len(sys.argv) > 4 else 1
        _out(finance(code, year, q))
    elif cmd == "basic":
        _out(stock_basic(sys.argv[2]))
    elif cmd == "industry":
        ind = industry()
        _out({k: v for k, v in list(ind.items())[:30]})
    elif cmd == "test":
        test()
    else:
        print("BaoStock Tool")
        print("Commands:")
        print("  kline <code> [days] [qfq|hfq|none]")
        print("  finance <code> [year] [quarter]")
        print("  basic <code>")
        print("  industry")
        print("  test")
        print("\nCode format: sz.000725 or sh.600888")
