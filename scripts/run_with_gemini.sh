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
export GEMINI_MODEL="${GEMINI_MODEL:-gemini-3.5-flash}"
export EMAIL_AGENT_BACKEND="${EMAIL_AGENT_BACKEND:-manual}"
export CHAT_WORKFLOW_BACKEND="${CHAT_WORKFLOW_BACKEND:-baseline}"

if [[ "$EMAIL_AGENT_BACKEND" != "manual" && "$EMAIL_AGENT_BACKEND" != "langchain" ]]; then
  printf "EMAIL_AGENT_BACKEND 只能是 manual 或 langchain。\n"
  exit 1
fi

if [[ "$CHAT_WORKFLOW_BACKEND" != "baseline" && "$CHAT_WORKFLOW_BACKEND" != "routing" ]]; then
  printf "CHAT_WORKFLOW_BACKEND 只能是 baseline 或 routing。\n"
  exit 1
fi

PYTHON_BIN="python3"
if [[ "$EMAIL_AGENT_BACKEND" == "langchain" ]]; then
  if [[ ! -x ".venv/bin/python" ]]; then
    printf "找不到 .venv；請先建立環境並安裝 requirements-week05.txt。\n"
    exit 1
  fi
  PYTHON_BIN=".venv/bin/python"
fi

printf "Email Agent Backend: %s\n" "$EMAIL_AGENT_BACKEND"
printf "Chat Workflow Backend: %s\n" "$CHAT_WORKFLOW_BACKEND"
"$PYTHON_BIN" app.py
