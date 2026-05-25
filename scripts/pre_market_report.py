#!/usr/bin/env python3
"""盘前分析报告生成器 — 生成 JPG 图片"""

import io, os, sys, json, math
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.font_manager import FontProperties
from collections import OrderedDict

# ── Config ──────────────────────────────────────────────────────
OUTPUT = r"C:\Users\Administrator\.openclaw\a-stock-kit\data\premarket_report.jpg"
FONT_PATH = r"C:\Windows\Fonts\msyh.ttc"
FONT_BOLD_PATH = r"C:\Windows\Fonts\msyhbd.ttc"
FONT_SIMHEI = r"C:\Windows\Fonts\simhei.ttf"

# 中文支持
plt.rcParams['font.family'] = 'Microsoft YaHei'
plt.rcParams['axes.unicode_minus'] = False

fp_normal = FontProperties(fname=FONT_PATH)
fp_bold = FontProperties(fname=FONT_BOLD_PATH)
fp_hei = FontProperties(fname=FONT_SIMHEI)

def fnt(size, bold=False):
    return ImageFont.truetype(FONT_BOLD_PATH if bold else FONT_PATH, size)

# ── Color Palette ───────────────────────────────────────────────
BG        = (20, 25, 40)      # 深蓝灰背景
CARD      = (32, 38, 58)      # 卡片色
ACCENT    = (70, 130, 255)    # 蓝
GREEN     = (0, 200, 120)     # 涨
RED       = (230, 70, 70)     # 跌
YELLOW    = (255, 190, 50)    # 黄
WHITE     = (230, 235, 245)
GRAY      = (140, 150, 170)
LIGHT     = (50, 58, 80)

# ── Stock Data (from Tencent API 5月22日收盘) ────────────────────
stocks = [
    {
        "name": "永利股份", "code": "300230", "price": 5.12, "change": 0.21,
        "pct": 4.28, "open": 4.97, "high": 5.13, "low": 4.91,
        "preclose": 4.91, "volume": "18.34万", "amount": 9260,
        "turnover": 2.91, "pe": 23.36, "industry": "塑料制品",
        "note": "连续两天放量上攻，逼近前高5.17"
    },
    {
        "name": "焦作万方", "code": "000612", "price": 12.47, "change": 0.62,
        "pct": 5.23, "open": 11.96, "high": 12.60, "low": 11.84,
        "preclose": 11.85, "volume": "49.07万", "amount": 60197,
        "turnover": 4.12, "pe": 10.47, "industry": "有色金属(铝)",
        "note": "放量突破箱体上沿，PE仅10.47估值优势明显"
    },
    {
        "name": "顺博合金", "code": "002996", "price": 7.30, "change": 0.33,
        "pct": 4.73, "open": 7.09, "high": 7.38, "low": 6.98,
        "preclose": 6.97, "volume": "14.00万", "amount": 10093,
        "turnover": 3.36, "pe": 21.15, "industry": "有色金属(再生铝)",
        "note": "放量反弹，布林带收窄待选择方向"
    }
]

# ── helpers ─────────────────────────────────────────────────────
def round_rect(draw, xy, r, fill, outline=None):
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle(xy, radius=r, fill=fill, outline=outline)

def draw_progress(draw, x, y, w, h, ratio, color):
    """绘制进度条"""
    draw.rounded_rectangle([x, y, x+w, y+h], radius=h//2,
                           fill=(50, 55, 75))
    fw = max(int(w * ratio), h)
    draw.rounded_rectangle([x, y, x+fw, y+h], radius=h//2,
                           fill=color)

def draw_table_row(draw, y, cols, col_widths, x_start, font):
    x = x_start
    for i, (v, align) in enumerate(cols):
        tw = font.getlength(str(v))
        if align == 'r':
            px = x + col_widths[i] - tw - 10
        elif align == 'c':
            px = x + (col_widths[i] - tw) / 2
        else:
            px = x + 10
        draw.text((px, y), str(v), fill=WHITE, font=font)
        x += col_widths[i]

# ── Build the Report Image ──────────────────────────────────────
W, H = 1200, 1680
img = Image.new('RGB', (W, H), BG)
draw = ImageDraw.Draw(img)

# ═══ Header ════════════════════════════════════════════════════
# 装饰顶栏
draw.rectangle([0, 0, W, 6], fill=ACCENT)

title_fnt = fnt(32, bold=True)
date_fnt  = fnt(16)
sub_fnt   = fnt(14)
sm_fnt    = fnt(13)
xs_fnt    = fnt(11)

draw.text((40, 20), "📊 盘前分析报告", fill=WHITE, font=title_fnt)
draw.text((40, 62), "周一 · 2026年5月25日 · 08:30", fill=GRAY, font=date_fnt)
draw.text((40, 84), "开盘前自动生成 | A股市场情绪与持仓分析", fill=GRAY, font=sub_fnt)

# 右上角风险提示
tip_box = [W-280, 22, W-30, 56]
round_rect(draw, tip_box, 8, LIGHT)
draw.text((W-270, 31), "⚠ 市场有风险，投资需谨慎", fill=YELLOW, font=sm_fnt)

# ═══ Section 1: 大盘情绪 ════════════════════════════════════════
y = 120
round_rect(draw, [30, y, W-30, y+200], 12, CARD)
draw.text((55, y+12), "📈 大盘情绪 — 上周五 (5月22日) 收盘", fill=ACCENT, font=fnt(18, bold=True))

# 四大指数
indices = [
    ("上证指数", 4112.90, "+0.87%", "✔"),
    ("深证成指", 15597.30, "+2.30%", "✔"),
    ("创业板指", 3938.50, "+2.84%", "✔"),
    ("科创50",   1790.77, "+1.51%", "✔"),
]
ix = 55
for name, val, pct, icon in indices:
    draw.rectangle([ix-8, y+44, ix+8, y+48], fill=ACCENT)
    draw.text((ix+16, y+40), name, fill=GRAY, font=sm_fnt)
    draw.text((ix+16, y+60), f"{val:,.2f}", fill=WHITE, font=fnt(16, bold=True))
    draw.text((ix+16, y+82), pct, fill=GREEN, font=sm_fnt)
    ix += 195

# 市场全景
my = y + 115
draw.text((55, my), "成交额：", fill=GRAY, font=sm_fnt)
draw.text((140, my), "29,247亿", fill=YELLOW, font=fnt(15, bold=True))
draw.text((55, my+22), "上涨：", fill=GRAY, font=sm_fnt)
draw.text((140, my+22), "3,869家", fill=GREEN, font=fnt(15, bold=True))
draw.text((280, my+22), "下跌：", fill=GRAY, font=sm_fnt)
draw.text((365, my+22), "1,509家", fill=RED, font=fnt(15, bold=True))
draw.text((510, my+22), "涨停：", fill=GRAY, font=sm_fnt)
draw.text((595, my+22), "136家", fill=GREEN, font=fnt(15, bold=True))
draw.text((730, my+22), "跌停：", fill=GRAY, font=sm_fnt)
draw.text((815, my+22), "18家", fill=RED, font=fnt(15, bold=True))

# 今日关注
draw.text((55, my+52), "⚠ 今日关注：", fill=YELLOW, font=sm_fnt)
notes = "外资休市（美股Memorial Day），沪深港通关闭 → 预计缩量，别指望大行情。DeepSeek永久降价 → 算力股承压。缩量反弹延续性有限，关注5/10/20日均线压力。"
draw.text((195, my+52), notes, fill=GRAY, font=sm_fnt)

# ═══ Section 2: 持仓个股分析 ═══════════════════════════════════
y = 340
round_rect(draw, [30, y, W-30, y+620], 12, CARD)
draw.text((55, y+12), "🔍 持仓个股深度扫描", fill=ACCENT, font=fnt(18, bold=True))

# 表头
h_y = y + 50
header_cols = [
    ("个股", 200, 'l'), ("现价", 100, 'r'), ("涨跌幅", 100, 'r'),
    ("换手率", 90, 'r'), ("成交额(万)", 110, 'r'), ("PE", 70, 'r'),
    ("操作建议", 260, 'l'),
]
hx = 55
hw = [200, 100, 100, 90, 110, 70, 260]
draw.text((55+200+100+100+90+110+70, h_y), "", fill=WHITE, font=sm_fnt)
draw_table_row(draw, h_y, [(c[0], c[2]) for c in header_cols], hw, 55, sub_fnt)

draw.line([(55, h_y+28), (W-55, h_y+28)], fill=LIGHT, width=1)

# 个股数据行
row_y = h_y + 42
for si, s in enumerate(stocks):
    bg_color = (40, 48, 72) if si % 2 == 0 else None
    if bg_color:
        draw.rounded_rectangle([40, row_y-4, W-40, row_y+42], 6, bg_color)

    pct_str = f"+{s['pct']:.2f}%"
    pct_color = GREEN

    # 涨跌幅
    amount_display = f"{s['amount']:,.0f}"
    pe_display = f"{s['pe']:.0f}"

    # 操作建议
    if s['code'] == '000612':
        advice = "✅ 核心持仓，放量突破，持有"
    elif s['code'] == '300230':
        advice = "✅ 缩量回踩企稳，今日观察量能"
    else:
        advice = "👀 放量反弹但需确认持续性"

    cols = [
        (f"{s['name']}({s['code']})", 'l'),
        (f"{s['price']:.2f}", 'r'),
        (pct_str, 'r'),
        (f"{s['turnover']:.2f}%", 'r'),
        (amount_display, 'r'),
        (pe_display, 'r'),
        (advice, 'l'),
    ]
    draw_table_row(draw, row_y, cols, hw, 55, sm_fnt)

    # 进度条 - 显示相对强度
    pb_x = 55
    pb_y = row_y + 24
    pb_w = 180
    pb_h = 4
    # 用涨幅比例做进度条
    ratio = min(s['pct'] / 10.0, 1.0)
    draw_progress(draw, pb_x, pb_y, pb_w, pb_h, ratio, pct_color)

    row_y += 50

# 仓位总览
my2 = row_y + 8
draw.line([(55, my2), (W-55, my2)], fill=LIGHT, width=1)
my2 += 18
draw.text((55, my2), "仓位建议：", fill=GRAY, font=sm_fnt)
draw.text((155, my2), "🔴 首推：焦作万方(000612) — 放量突破+低PE双核驱动", fill=GREEN, font=sm_fnt)
my2 += 24
draw.text((155, my2), "🟡 关注：永利股份(300230) — 观察能否突破前高5.17", fill=YELLOW, font=sm_fnt)
my2 += 24
draw.text((155, my2), "⚪ 辅助：顺博合金(002996) — 放量反弹，量能需持续", fill=GRAY, font=sm_fnt)

# ═══ Section 3: 当日策略要点 ════════════════════════════════════
y = 980
round_rect(draw, [30, y, W-30, y+260], 12, CARD)
draw.text((55, y+12), "📋 今日操作策略", fill=ACCENT, font=fnt(18, bold=True))

strategy_items = [
    ("集合竞价(9:15-9:25)", "外资休市，预计A股缩量震荡。9:20-9:25关注真实委托量。"),
    ("焦作万方", "12.47收盘，上周五放量突破5.23%。今日观察能否站稳12.50上方。如回踩12.30-12.40可考虑加仓。止损关注12.00整数关口。"),
    ("永利股份", "5.12收盘，逼近前高5.17。今日重点关注量能配合：早盘半小时成交>4000万 + 站稳5.15 = 有望突破。成交量不足则提防冲高回落。"),
    ("顺博合金", "7.30收盘，4.73%反弹。第一压力位7.40-7.50。需观察能否连续两天放量。如缩量回踩7.10以下则暂时观望。"),
    ("大盘信号", "上证4112点，缩量反弹修复。关注5日均线(约4130-4150)压力。深强沪弱特征明显，成长股率先反弹。万亿成交额是活跃锚点。"),
]

sy = y + 52
for title, content in strategy_items:
    draw.text((55, sy), f"▸ {title}", fill=YELLOW, font=sm_fnt)
    draw.text((55, sy+18), f"  {content}", fill=GRAY, font=xs_fnt)
    sy += 46

# ═══ Section 4: 量化指标 ═══════════════════════════════════════
y = 1260
round_rect(draw, [30, y, W-30, y+200], 12, CARD)
draw.text((55, y+12), "⚡ 量化指标速览", fill=ACCENT, font=fnt(18, bold=True))

# 两个set: 左侧+右侧
qt_y = y + 50
# 左侧
metrics_left = [
    ("涨跌比", "3,869/5,378 = 0.72", "普涨格局", GREEN),
    ("涨停/跌停", "136/18 = 7.6x", "做多情绪旺盛", GREEN),
    ("成交额变化", "2.92万亿 ↓0.58万亿", "缩量反弹，观望为主", YELLOW),
    ("涨停数评级", "136 > 100", "情绪偏亢奋，谨慎追高", YELLOW),
]
for i, (title, val, desc, color) in enumerate(metrics_left):
    ypos = qt_y + i * 36
    draw.text((55, ypos), title, fill=GRAY, font=sm_fnt)
    draw.text((155, ypos), val, fill=WHITE, font=sm_fnt)
    draw.text((350, ypos), desc, fill=color, font=sm_fnt)

# 右侧: 技术指标
tech_metrics = [
    ("上证日内支撑", "4,067 (60日均线)"),
    ("上证日内压力", "4,130-4,150 (5日/10日均线)"),
    ("量价核心判断", "缩量反弹 → 延续性存疑"),
    ("外资通道", "关闭 (Memorial Day)"),
]
qt_y2 = y + 52
for i, (title, val) in enumerate(tech_metrics):
    ypos = qt_y2 + i * 36
    draw.text((580, ypos), title, fill=GRAY, font=sm_fnt)
    draw.text((790, ypos), val, fill=WHITE, font=sm_fnt)

# ═══ Footer ════════════════════════════════════════════════════
y_footer = 1480
draw.line([(40, y_footer), (W-40, y_footer)], fill=LIGHT, width=1)
draw.text((40, y_footer+10), "🦞 小龙虾盘前分析 | 生成时间: 2026-05-25 08:30 CST", fill=GRAY, font=xs_fnt)
draw.text((40, y_footer+28), "*本报告基于公开数据自动生成，不构成投资建议。投资有风险，入市须谨慎。", fill=GRAY, font=xs_fnt)

# ── Save ────────────────────────────────────────────────────────
os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
img.save(OUTPUT, "JPEG", quality=92)
print("[OK] REPORT output: " + OUTPUT)
print("   Dimensions: {}x{}".format(img.size[0], img.size[1]))

sys.exit(0)
