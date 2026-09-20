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
