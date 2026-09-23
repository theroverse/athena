OUTPUT_DIRNAME = ".athena"

MANIFEST_FILENAME = "manifest.json"

TREE_DIRNAME = "tree"

# Extensao dos arquivos de resumo gerados pela Athena. Dedicada (em vez de
# ".md" puro) pra nao se confundir com documentacao real do projeto e pra
# dar um padrao de glob inequivoco (*.atn.md) pra quem consome o indice.
SUMMARY_EXTENSION = ".atn.md"

ROOT_SUMMARY_FILENAME = f"summary{SUMMARY_EXTENSION}"

ATHENAIGNORE_FILENAME = ".athenaignore"

# Nomes sempre ignorados, além do .gitignore/.athenaignore do projeto.
ALWAYS_IGNORED_NAMES = {
    ".git",
    OUTPUT_DIRNAME,
}

# Trunca arquivos muito grandes antes de mandar pro Claude, pra não
# estourar custo/tempo em um único arquivo gigante.
MAX_FILE_CHARS = 40_000

# Trava de segurança: recusa indexar mais que isso sem --max-files
# explícito, pra evitar rodar sem querer contra um repositório enorme
# (cada arquivo custa uma chamada real ao Claude).
DEFAULT_MAX_FILES = 300

# Quantos arquivos resumir em paralelo (thread pool; a chamada real ao
# Claude é I/O-bound via subprocess, não CPU, então threads bastam).
# Conservador de propósito: cada worker sobe um processo "claude -p"
# concorrente — um valor alto demais pode esbarrar em rate limit da
# API ou sobrecarregar a máquina.
DEFAULT_WORKERS = 4

# Resumir um arquivo/pasta é uma tarefa repetitiva e de baixo
# raciocínio (não é planejamento nem decisão de arquitetura), então
# por padrão usa o modelo mais leve/rápido em vez do modelo padrão da
# sessão do usuário (que pode ser um modelo caro). "--model" sobrepõe
# isso por chamada.
DEFAULT_SUMMARY_MODEL = "haiku"

# ---------------------------------------------------------------------------
# Backend local (Ollama) — inferência paralela totalmente offline.
# ---------------------------------------------------------------------------

# Qual backend usar quando o usuário não escolhe explicitamente:
# "auto" tenta o Ollama local e cai para o CLI do Claude se ele não
# estiver de pé. "local" força Ollama; "claude" força o CLI.
DEFAULT_BACKEND = "auto"

# Variáveis de ambiente que sobrepõem host/modelo do Ollama (lembre-se:
# o host é lido a cada chamada, então dá para apontar para outro
# servidor/portal num teste sem reiniciar o processo).
OLLAMA_HOST_ENV_VAR = "ATHENA_OLLAMA_HOST"
OLLAMA_MODEL_ENV_VAR = "ATHENA_OLLAMA_MODEL"

DEFAULT_OLLAMA_HOST = "http://localhost:11434"

# Um modelo compacto e comum (Llama/Qwen pequenos) roda offline em
# hardware modesto; "--model"/env sobrepõem por chamada.
DEFAULT_OLLAMA_MODEL = "llama3.2"

# Timeout generoso para geração (modelos locais podem ser lentos na
# primeira chamada, quando o modelo é carregado na memória).
OLLAMA_TIMEOUT = 120

# Timeout curto para o probe de disponibilidade ("o Ollama está de
# pé?"), feito no backend "auto" — não deve travar a indexação.
OLLAMA_PROBE_TIMEOUT = 3

# ---------------------------------------------------------------------------
# Memória local leve (banco vetorial / cache de contexto).
# ---------------------------------------------------------------------------

# Pasta de orquestração compartilhada do Theroverse na raiz do projeto
# (distinta de "~/.thero/tools", que é global). A Athena escreve sua
# memória em <projeto>/.thero/memory/.
MEMORY_DIRNAME = ".thero"
MEMORY_SUBDIR = "memory"
MEMORY_DB_FILENAME = "index.sqlite3"

# Top-k padrão devolvido por uma consulta de memória.
MEMORY_DEFAULT_TOP_K = 5
