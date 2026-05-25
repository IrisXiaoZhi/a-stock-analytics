"""Get today's top gainers using Tencent API batch queries"""
import urllib.request, json, re, sys
import pandas as pd

def get_top_gainers():
    """Fetch today's A-share rankings using Sina finance API"""
    try:
        # Use Sina new stock ranking API
        urls = [
            "https://money.finance.sina.com.cn/d/quotes_service/api/json_v2.php/RS_Index.getStockPage",
            "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/RS_Index.getStockPage"
        ]
        
        for base_url in urls:
            try:
                url = f"{base_url}?page=1&num=200&sort=changepercent&asc=0&node=hs_a&symbol=&_sra=&market="
                req = urllib.request.Request(url, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Referer': 'https://finance.sina.com.cn/'
                })
                resp = urllib.request.urlopen(req, timeout=10)
                text = resp.read().decode('gbk')
                
                # Try parsing as JSON
                if text.strip().startswith('{') or text.strip().startswith('['):
                    data = json.loads(text)
                    if isinstance(data, list) and len(data) > 0:
                        stocks = []
                        for item in data:
                            if isinstance(item, dict):
                                name = item.get('name', '')
                                code = item.get('code', '')
                                trade = float(item.get('trade', 0) or 0)
                                pct = float(item.get('changepercent', 0) or 0)
                                turnover = float(item.get('turnover', 0) or 0)
                                volume = float(item.get('volume', 0) or 0)
                                open_p = float(item.get('open', 0) or 0)
                                high = float(item.get('high', 0) or 0)
                                low = float(item.get('low', 0) or 0)
                                amount = float(item.get('amount', 0) or 0)
                                
                                stocks.append({
                                    '代码': code,
                                    '名称': name,
                                    '最新价': trade,
                                    '涨跌幅': pct,
                                    '换手率': turnover,
                                    '成交量': volume,
                                    '开盘价': open_p,
                                    '最高': high,
                                    '最低': low,
                                    '成交额': amount
                                })
                        
                        df = pd.DataFrame(stocks)
                        df = df[df['涨跌幅'] > 0]
                        df = df[df['涨跌幅'] <= 9.5]
                        df = df[df['涨跌幅'] >= 3]
                        return df.sort_values('涨跌幅', ascending=False)
            except:
                continue
    except:
        pass
    
    return pd.DataFrame()

# Test
df = get_top_gainers()
print(f"Got {len(df)} stocks matching criteria")
if not df.empty:
    for _, row in df.head(10).iterrows():
        print(f"  {row['名称']}({row['代码']}) p:{row['最新价']} pct:{row['涨跌幅']}% turnover:{row['换手率']}%")
else:
    print("No data from Sina API, trying alternative...")
    
    # Alternative: Parse from East Money HTML page
    try:
        import urllib.parse
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {
            'pn': '1', 'pz': '100', 'po': '1', 'np': '1',
            'fltt': '2', 'invt': '2', 'fid': 'f3',
            'fs': 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048',
            'fields': 'f12,f14,f2,f3,f15,f16,f17,f18'
        }
        url = url + '?' + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Referer': 'https://quote.eastmoney.com/'
        })
        resp = urllib.request.urlopen(req, timeout=10)
        text = resp.read().decode('utf-8')
        data = json.loads(text)
        items = data.get('data', {}).get('diff', [])
        print(f"EM API: got {len(items)} items")
        for item in items[:5]:
            print(f"  {item.get('f14','?')}({item.get('f12','?')}) p:{item.get('f2','?')} pct:{item.get('f3','?')}%")
    except Exception as e2:
        print(f"EM API also failed: {e2}")
