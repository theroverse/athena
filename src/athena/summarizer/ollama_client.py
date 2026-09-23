"""
Conector assíncrono para o Ollama local (inferência offline).

Stdlib-only de propósito (mesma regra do resto da Athena): as chamadas
são I/O-bound via HTTP, então `concurrent.futures.ThreadPoolExecutor`
paraleliza sem precisar de nenhuma biblioteca externa (nem `requests`,
nem o client oficial `ollama`). Nenhum dado sai da máquina: o host por
padrão é `localhost`.

Contrato espelha `claude_client.call_claude`: as funções de geração
retornam `str | None` (string limpa, ou `None` com um `[ERROR]` impresso
em falha), nunca levantando para o chamador.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from athena.settings import (
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    OLLAMA_HOST_ENV_VAR,
    OLLAMA_MODEL_ENV_VAR,
    OLLAMA_PROBE_TIMEOUT,
    OLLAMA_TIMEOUT,
)


def _host() -> str:
    # Lido a cada chamada (não no import) para que um teste possa
    # apontar para um servidor fake via monkeypatch de env sem
    # recarregar o módulo.
    return os.environ.get(OLLAMA_HOST_ENV_VAR, DEFAULT_OLLAMA_HOST).rstrip("/")


def _default_model() -> str:
    return os.environ.get(OLLAMA_MODEL_ENV_VAR, DEFAULT_OLLAMA_MODEL)


def _post(path: str, payload: dict, timeout: float) -> dict | None:
    """
    POST JSON e devolve o corpo decodificado, ou None em qualquer erro
    (conexão recusada, timeout, HTTP != 2xx, JSON inválido) com um
    `[ERROR]` amigável — o chamador nunca vê exceção crua.
    """

    url = f"{_host()}{path}"
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        print(f"[ERROR] Ollama HTTP {exc.code} em {path}.")
        return None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"[ERROR] Ollama inacessível em {url}: {exc}")
        return None

    try:
        return json.loads(body)
    except json.JSONDecodeError:
        print(f"[ERROR] Resposta do Ollama não é JSON válido (em {path}).")
        return None


def ollama_generate(
    prompt: str,
    *,
    model: str | None = None,
    timeout: float = OLLAMA_TIMEOUT,
) -> str | None:
    """Geração de texto simples (prompt → resposta) via /api/generate."""

    payload = {
        "model": model or _default_model(),
        "prompt": prompt,
        "stream": False,
    }
    result = _post("/api/generate", payload, timeout)

    if result is None:
        return None

    response = result.get("response")

    if not response or not response.strip():
        print("[ERROR] Ollama retornou resposta vazia.")
        return None

    return response.strip()


def ollama_chat(
    messages: list[dict],
    *,
    model: str | None = None,
    timeout: float = OLLAMA_TIMEOUT,
) -> str | None:
    """
    Conversa via /api/chat. `messages` no formato Ollama:
    `[{"role": "user", "content": "..."}]`.
    """

    payload = {
        "model": model or _default_model(),
        "messages": messages,
        "stream": False,
    }
    result = _post("/api/chat", payload, timeout)

    if result is None:
        return None

    content = (result.get("message") or {}).get("content")

    if not content or not content.strip():
        print("[ERROR] Ollama retornou conversa vazia.")
        return None

    return content.strip()


def ollama_embed(
    text: str,
    *,
    model: str | None = None,
    timeout: float = OLLAMA_TIMEOUT,
) -> list[float] | None:
    """
    Vetor de embedding via /api/embeddings (usado pela memória local
    para busca por similaridade de cosseno). `None` se indisponível — a
    memória cai para o fallback TF-IDF nesse caso.
    """

    payload = {
        "model": model or _default_model(),
        "prompt": text,
    }
    result = _post("/api/embeddings", payload, timeout)

    if result is None:
        return None

    embedding = result.get("embedding")

    if not embedding:
        print("[ERROR] Ollama retornou embedding vazio.")
        return None

    return [float(value) for value in embedding]


def is_available(*, timeout: float = OLLAMA_PROBE_TIMEOUT) -> bool:
    """
    Probe barato ("o Ollama está de pé?") usado pelo backend "auto".
    GET /api/tags sem capturar output; qualquer erro de rede → False.
    Silencioso de propósito: indisponibilidade aqui é o caminho normal
    (fallback para Claude), não um erro a reportar.
    """

    url = f"{_host()}/api/tags"

    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def call_many(
    prompts: list[str],
    *,
    model: str | None = None,
    max_workers: int = 4,
    timeout: float = OLLAMA_TIMEOUT,
) -> list[str | None]:
    """
    Gera várias respostas em paralelo (thread pool), preservando a ordem
    de `prompts` na saída. Cada chamada é I/O (HTTP) então threads
    bastam para sobrepor a latência dos modelos locais sem competir por
    GIL. Falha em uma prompt não derruba as demais (vira None naquele
    índice).
    """

    if not prompts:
        return []

    if max_workers <= 1:
        return [
            ollama_generate(prompt, model=model, timeout=timeout)
            for prompt in prompts
        ]

    with ThreadPoolExecutor(max_workers=min(max_workers, len(prompts))) as executor:
        futures = [
            executor.submit(
                ollama_generate,
                prompt,
                model=model,
                timeout=timeout,
            )
            for prompt in prompts
        ]
        return [future.result() for future in futures]
