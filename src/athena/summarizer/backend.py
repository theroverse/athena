from __future__ import annotations

"""
Camada única de roteamento de backend para as chamadas de resumo.

Hoje o indexador só falava com o CLI do Claude. Este módulo abstrai a
escolha entre dois backends:

- ``local``  → Ollama local (offline, barato, paralelo via HTTP).
- ``claude`` → CLI ``claude -p`` (comportamento histórico da Athena).

``backend="auto"`` decide por disponibilidade: se o Ollama está de pé,
usa ``local``; senão cai para ``claude``. Assim nada quebra para quem
não tem Ollama instalado, e quem tem passa a rodar offline sem trocar de
ferramenta.
"""

from pathlib import Path

from athena.settings import DEFAULT_BACKEND
from athena.summarizer import claude_client, ollama_client

# Aliases de modelo do Claude. Se o usuário deixar o --model padrão
# (ex.: "haiku") mas o backend resolvido for local, não faz sentido
# mandar esse alias para o Ollama — caímos para o modelo default do
# próprio Ollama (env ATHENA_OLLAMA_MODEL ou DEFAULT_OLLAMA_MODEL).
_CLAUDE_MODEL_ALIASES = {"haiku", "sonnet", "opus"}

LOCAL = "local"
CLAUDE = "claude"


def resolve_backend(backend: str = DEFAULT_BACKEND) -> str:
    """Normaliza 'auto' em 'local'/'claude' conforme disponibilidade."""

    if backend == LOCAL:
        return LOCAL

    if backend == CLAUDE:
        return CLAUDE

    # "auto" (e qualquer outro valor) → Ollama se acessível, senão Claude.
    return LOCAL if ollama_client.is_available() else CLAUDE


def summarize(
    prompt: str,
    *,
    backend: str = DEFAULT_BACKEND,
    model: str | None = None,
    cwd: Path | None = None,
) -> str | None:
    """
    Contrato único usado pelo indexador e pela API de contexto. Retorna
    `str | None` exatamente como `claude_client.call_claude`, então os
    chamadores não precisam saber qual backend serviu a resposta.
    """

    resolved = resolve_backend(backend)

    if resolved == LOCAL:
        local_model = None if model in _CLAUDE_MODEL_ALIASES else model
        return ollama_client.ollama_generate(prompt, model=local_model)

    return claude_client.call_claude(prompt, cwd=cwd, model=model)
