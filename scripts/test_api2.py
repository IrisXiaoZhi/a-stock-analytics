import urllib.request, json, sys

# Method 3: Try Sina API for top gainers
print("=== Sina API Sector/Industry ===")
url3 = 'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/RS_Index.getStockPage?page=1&num=500&sort=changepercent&asc=0&node=hs_a&symbol=&_sra=&market='
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://finance.sina.com.cn/'
}
try:
    req3 = urllib.request.Request(url3, headers=headers)
    resp3 = urllib.request.urlopen(req3, timeout=15)
    text = resp3.read().decode('gbk')
    data = json.loads(text)
    print(f'Sina API: Got {len(data)} items')
    for item in data[:10]:
        name = item.get('name', '?')
        code = item.get('code', '?')
        price = item.get('trade', '?')
        pct = item.get('changepercent', '?')
        turnover = item.get('turnover', '?')
        print(f"  {name}({code}) p:{price} pct:{pct}% turnover:{turnover}%")
except Exception as e:
    print(f'Sina API error: {e}')

# Method 4: Try Baostock for daily top gainers
print("\n=== Baostock check ===")
try:
    import baostock as bs
    import pandas as pd
    from datetime import datetime, timedelta
    bs.login()
    rs = bs.query_all_stock(datetime.now().strftime('%Y-%m-%d'))
    codes = []
    while rs.next():
        row = rs.get_row_data()
        codes.append(row)
    bs.logout()
    print(f'Baostock: got {len(codes)} stock codes')
except Exception as e:
    print(f'Baostock error: {e}')
