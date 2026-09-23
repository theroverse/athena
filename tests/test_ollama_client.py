from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from athena.summarizer import ollama_client

# ThreadingHTTPServer responde cada requisição em sua própria thread,
# então é o double certo para provar que call_many de fato concorre.
PEAK_CONCURRENCY = {"current": 0, "max": 0}
_LOCK = threading.Lock()


class _FakeOllamaHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silencia o log padrão p/ cada request
        pass

    def _send(self, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/tags":
            self._send({"models": [{"name": "llama3.2"}]})
        else:
            self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        request = json.loads(self.rfile.read(length) or b"{}")

        with _LOCK:
            PEAK_CONCURRENCY["current"] += 1
            PEAK_CONCURRENCY["max"] = max(
                PEAK_CONCURRENCY["max"], PEAK_CONCURRENCY["current"]
            )
        try:
            # Dorme um pouco para tornar observável a sobreposição de
            # requisições concorrentes no servidor threading.
            time.sleep(0.2)

            if self.path == "/api/generate":
                self._send({"response": "eco: " + request.get("prompt", "")})
            elif self.path == "/api/chat":
                messages = request.get("messages", [])
                last = messages[-1]["content"] if messages else ""
                self._send({"message": {"role": "assistant", "content": "oi " + last}})
            elif self.path == "/api/embeddings":
                self._send({"embedding": [0.1, 0.2, 0.3]})
            else:
                self.send_error(404)
        finally:
            with _LOCK:
                PEAK_CONCURRENCY["current"] -= 1


@pytest.fixture
def fake_ollama(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeOllamaHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host = f"http://127.0.0.1:{server.server_address[1]}"
    monkeypatch.setenv("ATHENA_OLLAMA_HOST", host)
    try:
        yield host
    finally:
        server.shutdown()
        server.server_close()


def test_ollama_generate_returns_stripped_response(fake_ollama):
    assert ollama_client.ollama_generate("ola") == "eco: ola"


def test_ollama_chat_returns_message_content(fake_ollama):
    result = ollama_client.ollama_chat([{"role": "user", "content": "mundo"}])
    assert result == "oi mundo"


def test_ollama_embed_returns_float_vector(fake_ollama):
    vector = ollama_client.ollama_embed("texto")
    assert vector == [0.1, 0.2, 0.3]
    assert all(isinstance(value, float) for value in vector)


def test_is_available_true_when_server_up(fake_ollama):
    assert ollama_client.is_available() is True


def test_call_many_preserves_order_and_returns_all(fake_ollama):
    results = ollama_client.call_many(["a", "b", "c"], max_workers=3)
    assert results == ["eco: a", "eco: b", "eco: c"]


def test_call_many_runs_concurrently(fake_ollama):
    PEAK_CONCURRENCY["max"] = 0
    ollama_client.call_many(["1", "2", "3", "4"], max_workers=4)
    # Se fosse sequencial, o pico observado seria 1; concorrência real
    # faz o servidor ver mais de uma requisição ao mesmo tempo.
    assert PEAK_CONCURRENCY["max"] > 1


def test_call_many_empty_returns_empty(fake_ollama):
    assert ollama_client.call_many([]) == []


def test_generate_returns_none_when_host_unreachable(monkeypatch):
    # Porta fechada: conexão recusada deve virar None, não exceção.
    monkeypatch.setenv("ATHENA_OLLAMA_HOST", "http://127.0.0.1:1")
    assert ollama_client.ollama_generate("x") is None


def test_is_available_false_when_host_unreachable(monkeypatch):
    monkeypatch.setenv("ATHENA_OLLAMA_HOST", "http://127.0.0.1:1")
    assert ollama_client.is_available(timeout=0.5) is False
