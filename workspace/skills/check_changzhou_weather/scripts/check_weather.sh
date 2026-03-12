#!/bin/bash
# 检查常州天气，返回温度
RESULT=$(curl -s "https://wttr.in/Changzhou?format=%t")
TEMP=$(echo "$RESULT" | tr -d '°C')
if (( $(echo "$TEMP > 10" | bc -l) )); then
    echo "alert:$TEMP"
else
    echo "cold:$TEMP"
fi