#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据上下文瘦身器：将超长结构化数据压缩为LLM安全摘要
输入：JSON/CSV 格式原始数据
输出：结构化 JSON 摘要，保留趋势、异常、关键指标
"""

import json
import pandas as pd
import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_data(data_str):
    try:
        data = json.loads(data_str)
        if isinstance(data, list):
            df = pd.DataFrame(data)
        elif isinstance(data, dict):
            df = pd.DataFrame([data])
        else:
            raise ValueError("Unsupported data format")
        return df
    except json.JSONDecodeError:
        # 尝试 CSV
        from io import StringIO
        df = pd.read_csv(StringIO(data_str))
        return df
    except Exception as e:
        logger.error(f"Failed to load data: {e}")
        raise


def summarize_dataframe(df):
    summary = {
        "total_rows": len(df),
        "total_columns": len(df.columns),
        "columns": {},
        "key_trends": [],
        "anomalies": [],
        "sample_rows": df.head(3).to_dict(orient='records') if len(df) > 0 else []
    }

    for col in df.columns:
        col_summary = {
            "dtype": str(df[col].dtype),
            "null_count": int(df[col].isnull().sum()),
            "unique_count": int(df[col].nunique())
        }

        # 数值型字段：统计均值、极值、标准差
        if pd.api.types.is_numeric_dtype(df[col]):
            col_summary.update({
                "mean": float(df[col].mean()) if not df[col].isnull().all() else None,
                "min": float(df[col].min()),
                "max": float(df[col].max()),
                "std": float(df[col].std()) if df[col].nunique() > 1 else None
            })
            
            # 异常检测：超过3倍标准差
            mean = df[col].mean()
            std = df[col].std()
            if std > 0:
                outliers = df[(df[col] > mean + 3*std) | (df[col] < mean - 3*std)]
                if len(outliers) > 0:
                    summary["anomalies"].append({
                        "column": col,
                        "type": "outlier",
                        "count": len(outliers),
                        "values": outliers[col].tolist()[:3]  # 只取前3个
                    })

        # 字符串型：高频词
        elif pd.api.types.is_object_dtype(df[col]):
            top_values = df[col].value_counts().head(5)
            col_summary["top_values"] = top_values.to_dict()

        summary["columns"][col] = col_summary

    # 检测时间趋势（如果存在时间列）
    time_cols = [col for col in df.columns if "time" in col.lower() or "date" in col.lower()]
    if time_cols:
        time_col = time_cols[0]
        df[time_col] = pd.to_datetime(df[time_col], errors='coerce')
        if not df[time_col].isnull().all():
            df_sorted = df.sort_values(time_col)
            first = df_sorted.iloc[0]
            last = df_sorted.iloc[-1]
            summary["key_trends"].append({
                "type": "time_trend",
                "time_column": time_col,
                "start": str(first[time_col]),
                "end": str(last[time_col]),
                "duration_hours": (last[time_col] - first[time_col]).total_seconds() / 3600
            })

    return summary


def main():
    if len(sys.argv) != 2:
        print("Usage: python summarize_data.py \"{your_data_json_or_csv}\"")
        sys.exit(1)

    data_str = sys.argv[1]
    df = load_data(data_str)
    summary = summarize_dataframe(df)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()