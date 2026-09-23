from __future__ import annotations

from unittest.mock import patch

from athena.summarizer import backend


def test_resolve_backend_forces_local():
    assert backend.resolve_backend("local") == "local"


def test_resolve_backend_forces_claude():
    assert backend.resolve_backend("claude") == "claude"


def test_resolve_backend_auto_picks_local_when_ollama_up():
    with patch("athena.summarizer.backend.ollama_client.is_available", return_value=True):
        assert backend.resolve_backend("auto") == "local"


def test_resolve_backend_auto_falls_back_to_claude_when_ollama_down():
    with patch("athena.summarizer.backend.ollama_client.is_available", return_value=False):
        assert backend.resolve_backend("auto") == "claude"


def test_summarize_local_uses_ollama_and_not_claude():
    with patch(
        "athena.summarizer.backend.ollama_client.ollama_generate",
        return_value="local summary",
    ) as mock_ollama, patch(
        "athena.summarizer.backend.claude_client.call_claude"
    ) as mock_claude:
        result = backend.summarize("prompt", backend="local")

    assert result == "local summary"
    mock_ollama.assert_called_once()
    mock_claude.assert_not_called()


def test_summarize_claude_uses_cli_and_not_ollama():
    with patch(
        "athena.summarizer.backend.claude_client.call_claude",
        return_value="claude summary",
    ) as mock_claude, patch(
        "athena.summarizer.backend.ollama_client.ollama_generate"
    ) as mock_ollama:
        result = backend.summarize("prompt", backend="claude")

    assert result == "claude summary"
    mock_claude.assert_called_once()
    mock_ollama.assert_not_called()


def test_summarize_local_drops_claude_alias_model_for_ollama():
    # "haiku" é alias do Claude; com backend local não deve ser enviado
    # ao Ollama — cai para None (o default do próprio Ollama).
    with patch(
        "athena.summarizer.backend.ollama_client.ollama_generate",
        return_value="ok",
    ) as mock_ollama:
        backend.summarize("prompt", backend="local", model="haiku")

    assert mock_ollama.call_args.kwargs["model"] is None


def test_summarize_local_keeps_explicit_ollama_model():
    with patch(
        "athena.summarizer.backend.ollama_client.ollama_generate",
        return_value="ok",
    ) as mock_ollama:
        backend.summarize("prompt", backend="local", model="qwen2.5")

    assert mock_ollama.call_args.kwargs["model"] == "qwen2.5"


def test_summarize_auto_resolves_and_dispatches():
    with patch(
        "athena.summarizer.backend.ollama_client.is_available", return_value=False
    ), patch(
        "athena.summarizer.backend.claude_client.call_claude",
        return_value="via claude",
    ) as mock_claude:
        result = backend.summarize("prompt", backend="auto")

    assert result == "via claude"
    mock_claude.assert_called_once()
