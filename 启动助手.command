#!/bin/zsh
# 双击即可启动「Pro Git 知识库助手」。
# 做的事：检查环境 → 端口已被占用就只开浏览器 → 否则起服务并自动打开页面。
# 关闭方式：在这个终端窗口按 Ctrl+C，或直接关掉窗口。

cd "$(dirname "$0")" || exit 1
PORT=8000
URL="http://127.0.0.1:$PORT"

echo "──────────────────────────────────────────"
echo " Pro Git 知识库助手"
echo "──────────────────────────────────────────"

# 1. 环境检查：虚拟环境或数据文件缺失时直接说明原因，别让用户对着报错猜
if [ ! -x ".venv/bin/python" ]; then
  echo "✗ 找不到 .venv/bin/python"
  echo "  请先在项目目录执行：python3 -m venv .venv && .venv/bin/pip install pymupdf numpy"
  echo
  read -r "?按回车关闭…"
  exit 1
fi

if [ ! -f "data/embeddings.npy" ] || [ ! -f "data/chunks.jsonl" ]; then
  echo "✗ 缺少索引文件 data/chunks.jsonl 或 data/embeddings.npy"
  echo "  请先运行：.venv/bin/python src/build_chunks.py && .venv/bin/python src/embed.py"
  echo
  read -r "?按回车关闭…"
  exit 1
fi

# 2. 如果服务已经在跑了（比如上次的窗口没关），不要重复起，直接开浏览器
if lsof -nP -iTCP:$PORT -sTCP:LISTEN >/dev/null 2>&1; then
  echo "服务已在运行，直接打开页面：$URL"
  open "$URL"
  echo
  echo "如需重启，先关掉那个窗口（或执行 lsof -ti tcp:$PORT | xargs kill）。"
  exit 0
fi

# 3. 起服务，3 秒后自动开浏览器（等索引加载完，不然页面会先报连不上）
( sleep 3; open "$URL" ) &

echo "正在启动，浏览器会自动打开…"
echo "停止服务：Ctrl+C"
echo

exec .venv/bin/python src/server.py $PORT
