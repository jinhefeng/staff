import akshare as ak
import json
import sys

def get_stock_data(symbol):
    try:
        # Fetch all A-share real-time data
        df = ak.stock_zh_a_spot_em()
        # Filter by symbol
        row = df[df['代码'] == str(symbol)]
        if len(row) == 0:
            return {"error": f"Symbol {symbol} not found."}
        
        # Extract fields
        price = float(row.iloc[0]['最新价'])
        change = float(row.iloc[0]['涨跌额'])
        pct_change = float(row.iloc[0]['涨跌幅'])
        volume = int(row.iloc[0]['成交量'])
        name = str(row.iloc[0]['名称'])
        
        return {
            'price': price,
            'change': change,
            'pct_change': pct_change,
            'volume': volume,
            'name': name
        }
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No symbol provided."}))
    else:
        symbol = sys.argv[1]
        result = get_stock_data(symbol)
        print(json.dumps(result, ensure_ascii=False))
