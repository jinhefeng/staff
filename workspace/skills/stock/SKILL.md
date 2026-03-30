---
description: Fetch real-time stock data for Chinese A-share companies.
metadata: {"nanobot": {"always": false}}
---
# Stock Analysis Skill

## Purpose
Fetch real-time stock data for Chinese A-share companies using AKShare (free, no API key required).

## Function
`get_stock_data(symbol)`

### Parameters
- `symbol`: Stock code in format `600128` (e.g., `600128` for 杭汽轮). No `.SS` suffix.

### Returns
Dictionary with:
- `price`: Current market price (float)
- `change`: Price change (absolute, float)
- `volume`: Trading volume (int)
- `name`: Company name (str)

### Dependencies
- `akshare`

### Example
```python
get_stock_data('600128')
```

### Notes
- Uses AKShare's `stock_zh_a_spot_em` interface for real-time A-share data.
- No API key required. Fully open and free.
- Fallback: Returns `None` if symbol invalid, network error, or no data.
- Supports all Shanghai/SZSE listed A-shares.

## Implementation
Use the built-in `shell` tool to execute the `stock.py` script located in the same directory.

```bash
python3 workspace/skills/stock/stock.py [symbol]
```

### Script Usage
The script returns a JSON string. Example call for '600128':
`python3 workspace/skills/stock/stock.py 600128`

### Source Code (stock.py)
The directory contains a persistent `stock.py` using `akshare`. DO NOT rewrite it unless updating logic.
