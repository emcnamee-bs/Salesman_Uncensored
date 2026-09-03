import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from astroturf.llm import LMStudioClient, LLMError


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence test output
        pass

    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/v1/models":
            self._send(200, {"data": [{"id": "qwen-a"}, {"id": "qwen-b"}]})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(length) or b"{}")
        if req.get("model") == "boom":
            self._send(500, {"error": "server exploded"})
            return
        if req.get("model") == "empty":
            self._send(200, {"choices": []})
            return
        self._send(
            200,
            {
                "choices": [
                    {"message": {"role": "assistant", "content": f"echo:{req['messages'][-1]['content'][:8]}"}}
                ]
            },
        )


@pytest.fixture()
def server():
    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/v1"
    httpd.shutdown()


def test_models_lists_ids(server):
    client = LMStudioClient(base_url=server)
    assert client.models() == ["qwen-a", "qwen-b"]


def test_chat_returns_content_stripped(server):
    client = LMStudioClient(base_url=server)
    out = client.chat("sys", "hello world there", model="qwen-a")
    assert out.startswith("echo:")


def test_chat_http_error_raises_llmerror(server):
    client = LMStudioClient(base_url=server)
    with pytest.raises(LLMError, match="500"):
        client.chat("s", "u", model="boom")


def test_chat_missing_choices_raises_llmerror(server):
    client = LMStudioClient(base_url=server)
    with pytest.raises(LLMError, match="no choices"):
        client.chat("s", "u", model="empty")


def test_chat_connection_error_raises_llmerror():
    client = LMStudioClient(base_url="http://127.0.0.1:9/v1", timeout=1)
    with pytest.raises(LLMError, match="connect"):
        client.chat("s", "u", model="x")
