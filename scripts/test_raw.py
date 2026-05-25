import urllib.request, json

url = 'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/RS_Index.getStockPage?page=1&num=5&sort=changepercent&asc=0&node=hs_a&symbol=&_sra=&market='
req = urllib.request.Request(url, headers={
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://finance.sina.com.cn/'
})
resp = urllib.request.urlopen(req, timeout=15)
text = resp.read().decode('gbk')
print("Raw response (first 1000 chars):")
print(text[:1000])
