# Stock Analysis Skill

## Purpose
Fetch real-time stock data for Chinese A-share companies (e.g. 杭汽轮, 阿里巴巴) using Yahoo Finance API.

## Function
`get_stock_data(symbol)`

### Parameters
- `symbol`: Stock code in format `XXXX.SS` (e.g. `600128.SS` for 杭汽轮)

### Returns
Dictionary with:
- `price`: Current market price
- `change`: Price change (absolute)
- `volume`: Trading volume

### Dependencies
- `requests`

### Example
```python
get_stock_data('600128.SS')
```

### Notes
- Uses public Yahoo Finance endpoint.
- No API key required.
- Only works for listed A-shares on Shanghai/SZSE.
- Fallback: Returns None if unreachable or invalid symbol.

## Implementation
```python
import requests

def get_stock_data(symbol):
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}.SS"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return None
    data = response.json()
    return {
        'price': data['chart']['result'][0]['meta']['regularMarketPrice'],
        'change': data['chart']['result'][0]['meta']['regularMarketChange'],
        'volume': data['chart']['result'][0]['meta']['regularMarketVolume']
    }
```