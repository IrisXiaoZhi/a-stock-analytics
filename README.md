# A-Stock Analytics 🦞

A股行情分析与量化策略回测工具，由 AI 助手小龙虾维护。

## 功能

- 📊 **行情数据获取** — BaoStock / AkShare 双数据源，支持日K线、实时行情
- 📈 **技术分析指标** — MA、MACD、RSI、布林带、量价分析
- 🌡️ **市场情绪监测** — 涨跌比、涨停跌停、成交额、四大指数快照
- 💰 **资金流向追踪** — 主力资金、北向资金、板块资金排名
- 🏆 **D1快枪选股** — 盘中扫描热点板块，筛选短线标的
- 📋 **盘前分析报告** — 开盘前自动生成深度研报
- ⚠️ **风险雷达** — ST/退市/解禁/质押/财务风险一票否决
- 🔄 **策略回测** — 基于历史K线的量化策略回测框架

## 快速开始

`ash
# 安装依赖
pip install -r requirements.txt

# 获取个股历史行情
python scripts/a_stock_tool.py history 300230 --days 120

# 技术指标分析
python scripts/a_stock_tool.py indicators 300230 --days 260

# 市场情绪扫描
python scripts/a_stock_extended.py sentiment

# 资金流向
python scripts/a_stock_extended.py fund-flow --type individual
`

## 注意
- 数据源可能延迟或变更，交易决策请以券商软件为准
- 本工具仅供学习研究，不构成投资建议
