from __future__ import annotations

from unittest.mock import patch

from athena.settings import DEFAULT_BACKEND, DEFAULT_SUMMARY_MODEL
from athena.summarizer import context


# -- clean_output (contrato "saída limpa", testável sem rede) ---------------


def test_clean_output_propagates_none():
    assert context.clean_output(None) is None


def test_clean_output_strips_leading_greeting():
    raw = "Claro, aqui está o resumo:\n- **Propósito**: faz X"
    cleaned = context.clean_output(raw)

    assert cleaned.startswith("- **Propósito**")
    assert "Claro" not in cleaned


def test_clean_output_strips_english_greeting():
    raw = "Sure! Here is the summary\nPropósito: Y"
    cleaned = context.clean_output(raw)

    assert "Sure" not in cleaned
    assert cleaned.startswith("Propósito")


def test_clean_output_drops_trailing_filler_lines():
    raw = (
        "- **Propósito**: indexa coisas\n"
        "- **API**: run()\n"
        "\n"
        "Espero ter ajudado! Qualquer dúvida, é só perguntar."
    )
    cleaned = context.clean_output(raw)

    assert cleaned.endswith("run()")
    assert "Espero ter ajudado" not in cleaned


def test_clean_output_removes_wrapping_fences():
    raw = "```markdown\n- **Propósito**: algo\n```"
    cleaned = context.clean_output(raw)

    assert "```" not in cleaned
    assert cleaned == "- **Propósito**: algo"


def test_clean_output_leaves_already_clean_text_untouched():
    raw = "- **Propósito**: resume arquivos\n- **Dependências**: backend"
    assert context.clean_output(raw) == raw


# -- summarize_code ----------------------------------------------------------


def test_summarize_code_routes_through_backend_and_cleans():
    with patch(
        "athena.summarizer.context.backend.summarize",
        return_value="Claro! Aqui vai:\n- **Propósito**: modulo X\n\nEspero ajudar.",
    ) as mock_summarize:
        result = context.summarize_code("def f(): pass", "src/x.py")

    assert result == "- **Propósito**: modulo X"
    prompt = mock_summarize.call_args.args[0]
    # Reusa o prompt canônico do indexador (contém marcadores do arquivo).
    assert "src/x.py" in prompt
    assert "def f(): pass" in prompt


def test_summarize_code_passes_backend_and_model_defaults():
    with patch(
        "athena.summarizer.context.backend.summarize", return_value="ok"
    ) as mock_summarize:
        context.summarize_code("code", "p.py")

    kwargs = mock_summarize.call_args.kwargs
    assert kwargs["backend"] == DEFAULT_BACKEND
    assert kwargs["model"] == DEFAULT_SUMMARY_MODEL


def test_summarize_code_forwards_explicit_backend():
    with patch(
        "athena.summarizer.context.backend.summarize", return_value="ok"
    ) as mock_summarize:
        context.summarize_code("code", "p.py", backend_name="local", model=None)

    assert mock_summarize.call_args.kwargs["backend"] == "local"


def test_summarize_code_returns_none_when_backend_fails():
    with patch("athena.summarizer.context.backend.summarize", return_value=None):
        assert context.summarize_code("code", "p.py") is None


# -- summarize_logs ----------------------------------------------------------


def test_summarize_logs_uses_log_prompt_and_cleans():
    with patch(
        "athena.summarizer.context.backend.summarize",
        return_value="Aqui está o resumo dos logs:\n- **O que aconteceu**: falhou\nFico à disposição.",
    ) as mock_summarize:
        result = context.summarize_logs("Traceback...\nError", source="ci")

    assert result == "- **O que aconteceu**: falhou"
    prompt = mock_summarize.call_args.args[0]
    assert "Traceback" in prompt
    assert "BEGIN LOGS" in prompt
