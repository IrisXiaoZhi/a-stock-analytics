#!/usr/bin/env python3
"""盘中监控三只股票价格，达到目标买入价时推送通知。"""

import json
import urllib.request
import datetime

# 监控目标价（老板同意的买入区间）
TARGETS = {
    "300230": {"name": "永利股份", "good": 5.08, "great": 5.00},
    "000612": {"name": "焦作万方", "good": 12.40, "great": 12.20},
    "002996": {"name": "顺博合金", "good": 7.20, "great": 7.10},
}

def get_quote(code):
    """从腾讯接口获取实时行情."""
    url = f"https://qt.gtimg.cn/q=sz{code}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    resp = urllib.request.urlopen(req, timeout=10)
    text = resp.read().decode("gbk")
    # 格式: v_szxxxxxx="...params..."
    if text.startswith("v_sz"):
        data = text.split('"')[1].split("~")
        price = float(data[3])  # 当前价
        pct = data[32]  # 涨跌幅%
        return {"price": price, "pct": pct}
    return None

def check_and_alert():
    now = datetime.datetime.now()
    # 只监控交易时间: 9:30-11:30, 13:00-15:00
    hm = now.hour * 100 + now.minute
    is_trading = (930 <= hm <= 1130) or (1300 <= hm <= 1500)
    if not is_trading:
        return  # 非交易时间跳过

    alerts = []
    for code, info in TARGETS.items():
        quote = get_quote(code)
        if quote is None:
            continue
        price = quote["price"]
        name = info["name"]
        good = info["good"]
        great = info["great"]

        if price <= great:
            alerts.append(f"[理想买点] {name}({code}) 现价 {price}，已达理想买点（≤{great}）！")
        elif price <= good:
            alerts.append(f"[建议区间] {name}({code}) 现价 {price}，进入建议区间（≤{good}）！")
        # 记录当前价到日志用于历史
        print(f"[{now.strftime('%H:%M')}] {name}: {price} (目标≤{good}/理想≤{great})")

    if alerts:
        alert_text = "\n".join(alerts)
        print(f"\n===== 买入提醒 =====\n{alert_text}", flush=True)
        # 写到文件让 cron 读取
        with open("C:\\Users\\Administrator\\.openclaw\\a-stock-kit\\data\\buy_alert.txt", "w", encoding="utf-8") as f:
            f.write(alert_text)

if __name__ == "__main__":
    check_and_alert()
