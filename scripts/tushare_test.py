"""Test Tushare Pro APIs - fund flow and dragon-tiger board"""
import tushare as ts
ts.set_token('07a21cbd898de0cd91499384e2593e31a0b32d0c7c825d9f456b3ebd')
pro = ts.pro_api()

# Test 1: Fund flow for our picks
print("=" * 60)
print("个股资金流向 (2026-05-22)")
print("=" * 60)
for code in ['000725.SZ','300230.SZ','000612.SZ','002996.SZ','000532.SZ','600888.SH']:
    try:
        df = pro.moneyflow(ts_code=code, start_date='20260522', end_date='20260522')
        if df is not None and not df.empty:
            r = df.iloc[0]
            net = float(r.get('net_mf_amt', 0) or 0)
            buy_lg = float(r.get('buy_lg_amt', 0) or 0)
            sell_lg = float(r.get('sell_lg_amt', 0) or 0)
            net_lg = buy_lg - sell_lg
            print(f'{code}: 主力净流入={net/1e4:.0f}万  大单净={net_lg/1e4:.0f}万')
        else:
            print(f'{code}: 无数据')
    except Exception as e:
        print(f'{code}: {str(e)[:50]}')

# Test 2: Dragon-tiger board
print("\n" + "=" * 60)
print("龙虎榜 (2026-05-22)")
print("=" * 60)
try:
    df = pro.top_list(trade_date='20260522')
    if df is not None and not df.empty:
        for _, r in df.iterrows():
            chg = r.get('pct_chg', '')
            amt = float(r.get('amount', 0) or 0)
            name = r.get('name', '')
            code = r.get('ts_code', '')
            if amt > 1e8:  # 成交额大于1亿
                print(f'{code} {name}  涨幅:{chg}%  成交:{amt/1e4:.0f}万')
except Exception as e:
    print(f'龙虎榜: {str(e)[:50]}')

# Test 3: Stock concepts for our picks
print("\n" + "=" * 60)
print("概念分类 (同花顺)")
print("=" * 60)
try:
    df = pro.ths_member(ts_code='000725.SZ')
    if df is not None and not df.empty:
        print(f'京东方A概念: {", ".join(df["con_code"].head(8).tolist())}')
except Exception as e:
    # Try concept instead
    try:
        df = pro.concept()
        print(f'概念板块总数: {len(df)}')
    except:
        print(f'概念: {str(e)[:50]}')

print("\nTushare Pro 配置完成!")
