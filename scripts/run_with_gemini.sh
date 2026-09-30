#!/usr/bin/env bash
set -u

printf "Gemini API Key（輸入內容不會顯示或寫入檔案）: "
IFS= read -r -s GEMINI_API_KEY
printf "\n"

if [ -z "$GEMINI_API_KEY" ]; then
  printf "未輸入 Key，已取消啟動。\n"
  exit 1
fi

if [[ ! "$GEMINI_API_KEY" =~ ^[A-Za-z0-9._-]+$ ]]; then
  printf "Key 格式不正確：請只貼上 Google AI Studio 顯示的 Key 本體，不要包含引號、空格、中文標點或 GEMINI_API_KEY=。\n"
  exit 1
fi

export GEMINI_API_KEY
export GEMINI_MODEL="${GEMINI_MODEL:-gemini-3.8-flash}"
python3 app.py
