from __future__ import annotations

"""
API de resumo de contexto da Athena — saída enxuta, sem ruído conversacional.

Funções de alto nível para comprimir logs e trechos de código no formato
que outras IAs consomem sem ruído (propósito, API pública, dependências,
pontos de atenção). Roteiam pelo ``backend.summarize`` (default ``auto``,
que prefere o Ollama local e cai para o Claude quando ele não está de pé),
reusando os prompts canônicos de ``summarizer/prompts.py``.

Além de montar o prompt certo, cada função passa a resposta por um
``clean_output`` determinístico que remove aberturas/fechos de cortesia e
markdown fences acidentais. O objetivo é garantir que **nenhum ruído
conversacional** vaze para os agentes downstream, mesmo que o modelo
escolhido insista em ser educado demais.
"""

import re

from athena.settings import DEFAULT_BACKEND, DEFAULT_SUMMARY_MODEL
from athena.summarizer import backend
from athena.summarizer.prompts import FILE_SUMMARY_PROMPT, LOG_SUMMARY_PROMPT

# Aberturas de cortesia comuns (PT/EN) que nunca devem abrir um resumo.
# Casa a LINHA inteira de preâmbulo (ex.: "Claro, aqui está o resumo:",
# "Sure! Here is the summary") — o corpo real de markdown começa na
# próxima linha. Exigir que a linha inteira seja preâmbulo evita descascar
# um item legítimo que apenas comece com uma dessas palavras.
_LEADING_FILLER_LINE = re.compile(
    r"^\s*(?:claro|certo|com\s+certeza|perfeito|ótimo|ótima|"
    r"aqui\s+(?:está|esta|estão|vai|segue)|segue\s+(?:abaixo|o|a|em)|"
    r"sure|certainly|of\s+course|here(?:'|’)?s\b|here\s+is|"
    r"below\s+is|this\s+(?:is|resumo))\b[^\n]*$",
    re.IGNORECASE,
)

# Linhas inteiras de fechamento/rodapé conversacional para descartar.
_TRAILING_FILLER = re.compile(
    r"^\s*(?:espero\s+(?:ter\s+)?(?:isso\s+)?(?:ajud|esclarec)|"
    r"qualquer\s+(?:d[uú]vida|pergunta|outra\s+coisa)|"
    r"fico\s+[àa]\s+disp[oó]s|abrac[oa]s?|att\.?|"
    r"(?:let\s+me|é\s+s[oó]\s+)|feel\s+free\s+to|happy\s+to\s+help|"
    r"if\s+you\s+(?:need|want))",
    re.IGNORECASE,
)

_FENCE = re.compile(r"^\s*(```|~~~)")


def clean_output(text: str | None) -> str | None:
    """
    Remove ruído conversacional de uma resposta de modelo:

    - markdown fences de abertura/fechamento,
    - uma possível frase inicial de cortesia ("Claro, aqui está ...:"),
    - linhas de rodapé do tipo "espero ter ajudado / let me know".

    É puramente textual e determinístico — nenhum acesso à rede — para
    que o contrato "saída limpa" seja verificável em testes unitários.
    ``None`` (fallback silencioso do backend) é propagado sem alterar.
    """

    if text is None:
        return None

    lines = text.splitlines()

    # 1) Tira fences ```/~~~ que cercam o corpo inteiro, se existirem.
    while lines and _FENCE.match(lines[0]):
        lines = lines[1:]
    while lines and _FENCE.match(lines[-1]):
        lines = lines[:-1]

    # 2) Remove linhas de fechamento conversacional do fim.
    while lines and (_TRAILING_FILLER.match(lines[-1]) or not lines[-1].strip()):
        lines = lines[:-1]

    # 3) Descasca uma linha inicial de cortesia, se for preâmbulo puro.
    while lines and _LEADING_FILLER_LINE.match(lines[0]):
        lines = lines[1:]

    body = "\n".join(lines)

    # 4) Normaliza espaços/linhas vazias nas bordas.
    return body.strip()


def summarize_code(
    snippet: str,
    path: str,
    *,
    backend_name: str = DEFAULT_BACKEND,
    model: str | None = DEFAULT_SUMMARY_MODEL,
) -> str | None:
    """
    Resume UM trecho de código no formato canônico da Athena (propósito,
    API pública, dependências, pontos de atenção), com saída limpa.
    Reusa exatamente o mesmo prompt do indexador, então o resultado é
    homogêneo ao do índice em disco.
    """

    prompt = FILE_SUMMARY_PROMPT.format(relative_path=path, content=snippet)
    summary = backend.summarize(prompt, backend=backend_name, model=model)

    return clean_output(summary)


def summarize_logs(
    text: str,
    *,
    source: str = "",
    backend_name: str = DEFAULT_BACKEND,
    model: str | None = DEFAULT_SUMMARY_MODEL,
) -> str | None:
    """
    Condensa logs/saída de execução num resumo técnico direto (resultado,
    erros relevantes, suspeita de causa, próximos passos), sem qualquer
    framing conversacional.
    """

    prompt = LOG_SUMMARY_PROMPT.format(source=source, content=text)
    summary = backend.summarize(prompt, backend=backend_name, model=model)

    return clean_output(summary)
