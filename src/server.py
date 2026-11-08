"""把 GitDocsAgent 包成一个网页聊天服务（标准库实现，零新增依赖）。

启动：
    .venv/bin/python src/server.py            # http://127.0.0.1:8000
    .venv/bin/python src/server.py 8080       # 换端口

接口：
    GET  /                 返回 web/index.html
    POST /api/chat         {"session": "...", "question": "..."} → SSE 流
    POST /api/reset        {"session": "..."} → 清空该会话历史

SSE 事件：
    event: trace   data: {"query","top_k","hits":[...]}   每次检索一行
    event: answer  data: {"answer": "..."}                最终答案
    event: warn    data: {"warnings": ["..."]}            参数核对告警
    event: error   data: {"message": "..."}               出错

设计说明：
- 每个浏览器会话对应一个 GitDocsAgent 实例（各自独立的对话历史），存在 SESSIONS 字典里。
  805 块向量只有 3.3MB，多开几个会话内存无压力。
- ask() 是阻塞的（内部可能串行调两次检索），所以丢进子线程跑，
  主线程从 queue 里取事件实时推给浏览器，避免「转圈 20 秒」。
- 只监听 127.0.0.1，不对外暴露。
"""
from __future__ import annotations

import json
import queue
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent import GitDocsAgent  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web" / "index.html"

SESSIONS: dict[str, GitDocsAgent] = {}
LOCK = threading.Lock()
# 本次进程的启动标识：前端拿它判断「服务是不是重启过」，重启后内存里的会话全没了，
# 界面上残留的旧对话就成了幽灵，必须让前端清掉
BOOT_ID = uuid.uuid4().hex


def get_agent(session_id: str) -> GitDocsAgent:
    """取会话对应的 agent，没有就新建；加锁防并发重复创建。"""
    with LOCK:
        agent = SESSIONS.get(session_id)
        if agent is None:
            agent = GitDocsAgent()
            SESSIONS[session_id] = agent
        return agent


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # 静音默认的每条请求日志，只保留关键错误
    def log_message(self, fmt: str, *args) -> None:
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/hello":
            body = json.dumps({"boot": BOOT_ID, "sessions": len(SESSIONS)}).encode()
            self._send(200, body, "application/json")
            return
        if self.path in ("/", "/index.html"):
            if not WEB.exists():
                self._send(500, b"web/index.html not found", "text/plain; charset=utf-8")
                return
            self._send(200, WEB.read_bytes(), "text/html; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send(400, b'{"error":"bad json"}', "application/json")
            return

        if self.path == "/api/reset":
            session = str(payload.get("session") or "")
            with LOCK:
                agent = SESSIONS.get(session)
            if agent:
                agent.reset()
            self._send(200, b'{"ok":true}', "application/json")
            return

        if self.path == "/api/chat":
            self.handle_chat(payload)
            return

        self._send(404, b"not found", "text/plain; charset=utf-8")

    def handle_chat(self, payload: dict) -> None:
        question = str(payload.get("question") or "").strip()
        session = str(payload.get("session") or uuid.uuid4().hex)
        if not question:
            self._send(400, b'{"error":"empty question"}', "application/json")
            return

        agent = get_agent(session)
        events: queue.Queue = queue.Queue()
        result: dict[str, str] = {}

        def run() -> None:
            try:
                result["answer"] = agent.ask(question)
            except Exception as exc:  # 网络/接口错误都在这兜住，转成 SSE error 事件
                result["error"] = f"{type(exc).__name__}: {exc}"
            finally:
                events.put(("done", {}))

        agent.trace_hook = lambda data: events.put(("trace", data))
        worker = threading.Thread(target=run, daemon=True)
        worker.start()

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        def emit(event: str, data: dict) -> None:
            self.wfile.write(f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode())
            self.wfile.flush()

        try:
            emit("session", {"session": session})
            while True:
                kind, data = events.get()
                if kind == "done":
                    break
                emit(kind, data)

            worker.join(timeout=5)
            if "error" in result:
                emit("error", {"message": result["error"]})
            else:
                if agent.last_warnings:
                    emit("warn", {"warnings": agent.last_warnings})
                emit("answer", {"answer": result.get("answer", "")})
        except (BrokenPipeError, ConnectionResetError):
            # 用户中途关页面：子线程继续跑完也无害，历史照常保留
            pass


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    if not WEB.exists():
        raise SystemExit(f"找不到前端文件：{WEB}")
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Pro Git 知识库助手已启动：http://127.0.0.1:{port}")
    print("Ctrl+C 停止。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")


if __name__ == "__main__":
    main()
