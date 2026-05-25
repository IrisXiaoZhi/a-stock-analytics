import urllib.request, json, sys

# Method 1: East Money API
url = 'https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=10&po=1&np=1&fltt=2&invt=2&fid=f3&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048&fields=f12,f14,f2,f3,f17,f18'
req = urllib.request.Request(url, headers={
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://quote.eastmoney.com/'
})
try:
    resp = urllib.request.urlopen(req, timeout=10)
    data = json.loads(resp.read().decode('utf-8'))
    diffs = data.get('data', {}).get('diff', [])
    print(f'East Money API: {len(diffs)} items')
    for item in diffs[:5]:
        print(f"  {item.get('f14','?')}({item.get('f12','?')}) p:{item.get('f2','?')} pct:{item.get('f3','?')}%")
except Exception as e:
    print(f'East Money error: {e}')

# Method 2: Tencent API  
print('\nTencent API test:')
url2 = 'https://qt.gtimg.cn/q=sz300230,sz000612,sz002996,sh600519'
req2 = urllib.request.Request(url2, headers={'User-Agent': 'Mozilla/5.0'})
resp2 = urllib.request.urlopen(req2, timeout=10)
print(resp2.read().decode('gbk')[:500])
