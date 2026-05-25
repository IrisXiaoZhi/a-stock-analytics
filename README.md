# A Stock Kit for OpenClaw

This local kit supports OpenClaw skills for China A-share research. It is for analysis, journaling, screening, and risk checks. It does not place orders or control a broker app.

## Runtime

Use the bundled virtual environment:

```powershell
C:\Users\Administrator\.openclaw\a-stock-kit\.venv\Scripts\python.exe C:\Users\Administrator\.openclaw\a-stock-kit\scripts\a_stock_tool.py --help
```

## Common commands

```powershell
# Fetch recent history and indicators
python scripts\a_stock_tool.py history 600519 --days 120
python scripts\a_stock_tool.py indicators 600519 --days 180

# Risk scan
python scripts\a_stock_tool.py risk 600519

# Moving average backtest
python scripts\a_stock_tool.py backtest-ma 600519 --fast 20 --slow 60 --days 900

# Watchlist
python scripts\a_stock_tool.py watchlist-add core 600519 贵州茅台
python scripts\a_stock_tool.py watchlist-scan core

# Journal
python scripts\a_stock_tool.py journal-add 600519 buy 100 1800 --reason "test plan"
python scripts\a_stock_tool.py journal-list
```

## Data notes

Data sources such as AkShare may change endpoints or field names. Treat output as decision support, not a trading instruction. Always verify important numbers with the broker, exchange, or official announcement.
