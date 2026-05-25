"""Get top gainers from multiple sources"""
import urllib.request, json, re

def sina_top_gainers():
    """Get top gainers from Sina finance"""
    url = 'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/RS_Index.getStockPage'
    params = '?page=1&num=100&sort=changepercent&asc=0&node=hs_a&symbol=&_sra=&market='
    
    req = urllib.request.Request(url+params, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://finance.sina.com.cn/'
    })
    resp = urllib.request.urlopen(req, timeout=15)
    text = resp.read().decode('gbk')
    
    data = json.loads(text)
    stocks = []
    for item in data:
        name = item.get('name', '')
        code = item.get('code', '')
        price = float(item.get('trade', 0) or 0)
        pct = float(item.get('changepercent', 0) or 0)
        turnover = float(item.get('turnover', 0) or 0)
        volume = float(item.get('volume', 0) or 0)
        
        stocks.append({
            'code': code,
            'name': name,
            'price': price,
            'pct': pct,
            'turnover': turnover,
            'volume': volume
        })
    
    return stocks

def tencent_gainer_list():
    """Get list of stocks ranked by volume/sort from Tencent"""
    # Tencent's batch quote endpoint for top gainers
    # Use individual stock batch queries
    url = 'https://qt.gtimg.cn/q=r_sh.000001'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    resp = urllib.request.urlopen(req, timeout=10)
    return resp.read().decode('gbk')[:500]

# Test
print("Testing Sina top gainers...")
try:
    stocks = sina_top_gainers()
    print(f"Got {len(stocks)} stocks")
    for s in stocks[:5]:
        print(f"  {s['name']}({s['code']}) p:{s['price']} pct:{s['pct']}% turnover:{s['turnover']}%")
except Exception as e:
    print(f"Sina error: {e}")
    import traceback
    traceback.print_exc()
