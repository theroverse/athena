from __future__ import annotations

import argparse
import sys
from pathlib import Path

from athena.ignore import build_matcher
from athena.manifest import Manifest
from athena.memory import MemoryStore
from athena.memory.store import VALID_KINDS
from athena.settings import (
    ATHENAIGNORE_FILENAME,
    DEFAULT_BACKEND,
    DEFAULT_MAX_FILES,
    DEFAULT_SUMMARY_MODEL,
    DEFAULT_WORKERS,
    MEMORY_DEFAULT_TOP_K,
    OUTPUT_DIRNAME,
    ROOT_SUMMARY_FILENAME,
    SUMMARY_EXTENSION,
    TREE_DIRNAME,
)
from athena.summarizer import ollama_client
from athena.summarizer.backend import resolve_backend
from athena.summarizer.indexer import (
    IndexStats,
    build_tree,
    count_files,
    summarize_dir,
    summarize_files_parallel,
)
from athena.system.process import command_exists, hide_windows_path

HELP_EPILOG = r"""
REQUISITOS
    Python 3.10+
    Claude Code instalado e autenticado ("claude -p")

COMANDOS
    index [PASTA]      Gera/atualiza o indice de resumos recursivos
                       do projeto em PASTA (padrao: pasta atual).
    show <caminho>     Mostra o resumo ja indexado de um arquivo ou
                       pasta (caminho relativo ao projeto). Use "."
                       para o resumo raiz do projeto.
    remember <kind> <arquivo>
                       Guarda o conteudo de <arquivo> na memoria local
                       (.thero/memory/) como convengao/historico/
                       decisao/nota. <kind> e um desses quatro.
    recall <consulta>  Busca por similaridade na memoria local e
                       imprime os registros mais relevantes.
    -h, --help         Mostra esta ajuda e sai, sem indexar nada e
                       sem chamar o Claude.

COMO FUNCIONA
    A Athena resume cada arquivo do projeto usando o Claude Code
    ("claude -p"), de baixo para cima: primeiro cada arquivo, depois
    cada pasta (a partir dos resumos dos seus arquivos/subpastas),
    ate chegar num resumo da raiz do projeto. Cada resumo fica em
    .athena/tree/<caminho>.atn.md (arquivos) ou
    .athena/tree/<caminho>/_dir_summary.atn.md (pastas), espelhando a
    estrutura do projeto. Um cache (.athena/manifest.json) guarda o
    hash de cada item ja resumido, entao rodar de novo so re-resume o
    que mudou.

    Respeita o .gitignore da raiz do projeto e, opcionalmente, um
    .athenaignore (mesma sintaxe) para exclusoes extras. .git/ e
    .athena/ sao sempre ignorados.

CUSTO / SEGURANCA
    Cada arquivo/pasta novo ou modificado gera uma chamada real ao
    Claude. Por seguranca, "index" recusa rodar contra mais de %s
    arquivos de uma vez, a menos que voce passe --max-files com um
    numero maior. Use --dry-run para ver o que seria processado sem
    gastar nenhuma chamada.

PARALELISMO (--workers)
    Arquivos nao tem dependencia entre si (so pastas dependem dos
    resumos dos filhos), entao sao resumidos em paralelo num thread
    pool antes do passo de pastas — %s de cada vez por padrao. Use
    --workers 1 pra voltar ao comportamento sequencial (ex.: pra
    debugar a saida linha a linha) ou um numero maior pra acelerar
    ainda mais, com cuidado pra nao esbarrar em rate limit da API.

MODELO (--model)
    Resumir e tarefa repetitiva de baixo raciocinio, entao por padrao
    usa um modelo leve/rapido em vez do modelo da sessao atual do
    Claude Code (que pode ser mais caro). Passe --model "" pra usar o
    modelo padrao da sessao, ou --model <alias/nome> pra escolher
    outro.

EXEMPLOS
    python athena.py index
    python athena.py index --dry-run
    python athena.py index /caminho/do/projeto
    python athena.py index --force
    python athena.py index --max-files 1000
    python athena.py index --workers 8
    python athena.py index --model ""
    python athena.py show src/components/Button.tsx
    python athena.py show src/components
    python athena.py show .
    python athena.py remember decision docs/adr-001.md
    python athena.py recall "como funciona o cache incremental"
    python athena.py --help
"""


def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        prog="athena.py",
        description=(
            "Indexador recursivo de resumos de projeto para uso "
            "como contexto de IA (via Claude Code)."
        ),
        epilog=HELP_EPILOG % (DEFAULT_MAX_FILES, DEFAULT_WORKERS),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command")

    index_parser = subparsers.add_parser(
        "index",
        help="Gera/atualiza o indice de resumos do projeto.",
    )
    index_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Pasta do projeto a indexar (padrao: pasta atual).",
    )
    index_parser.add_argument(
        "--force",
        action="store_true",
        help="Ignora o cache e re-resume tudo.",
    )
    index_parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Mostra o que seria processado, sem chamar o Claude "
            "nem escrever nada em disco."
        ),
    )
    index_parser.add_argument(
        "--max-files",
        type=int,
        default=DEFAULT_MAX_FILES,
        help=(
            "Numero maximo de arquivos permitido antes de recusar "
            f"rodar (padrao: {DEFAULT_MAX_FILES})."
        ),
    )
    index_parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        metavar="N",
        help=(
            "Quantos arquivos resumir em paralelo (padrao: "
            f"{DEFAULT_WORKERS}). 1 desativa o paralelismo. Cada "
            "worker sobe um \"claude -p\" concorrente; um numero "
            "alto demais pode esbarrar em rate limit."
        ),
    )
    index_parser.add_argument(
        "--model",
        default=DEFAULT_SUMMARY_MODEL,
        metavar="MODELO",
        help=(
            "Modelo usado nas chamadas ao Claude para resumir "
            f'(padrao: "{DEFAULT_SUMMARY_MODEL}" — resumir e tarefa '
            "repetitiva, nao precisa do modelo mais caro/forte da "
            "sessao). Aceita alias (\"haiku\", \"sonnet\", \"opus\") "
            "ou nome completo do modelo. Vazio (\"\") usa o modelo "
            "padrao da sessao do Claude Code. Com --backend local, "
            "aliases do Claude sao ignorados e vale o modelo do Ollama "
            "(--model <nome-ollama> ou ATHENA_OLLAMA_MODEL)."
        ),
    )
    index_parser.add_argument(
        "--backend",
        choices=["auto", "local", "claude"],
        default=DEFAULT_BACKEND,
        metavar="BACKEND",
        help=(
            "Onde as chamada de resumo roda: 'local' usa o Ollama "
            "offline; 'claude' usa o CLI claude -p (comportamento "
            f"historico); 'auto' (padrao) usa Ollama se estiver de "
            "pe, senao Claude."
        ),
    )

    show_parser = subparsers.add_parser(
        "show",
        help="Mostra um resumo ja indexado.",
    )
    show_parser.add_argument(
        "target",
        help=(
            "Caminho relativo (arquivo ou pasta) a mostrar. Use "
            '"." para o resumo raiz do projeto.'
        ),
    )
    show_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Pasta do projeto indexado (padrao: pasta atual).",
    )

    remember_parser = subparsers.add_parser(
        "remember",
        help="Indexa uma decisao/convencao/historico na memoria local.",
    )
    remember_parser.add_argument(
        "kind",
        choices=sorted(VALID_KINDS),
        help=(
            "Tipo do registro: "
            + ", ".join(sorted(VALID_KINDS))
            + "."
        ),
    )
    remember_parser.add_argument(
        "arquivo",
        help=(
            "Arquivo cujo conteudo sera guardado como memoria "
            "(caminho relativo a --path ou absoluto)."
        ),
    )
    remember_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Pasta do projeto dona da memoria (padrao: atual).",
    )
    remember_parser.add_argument(
        "--backend",
        choices=["auto", "local", "claude"],
        default=DEFAULT_BACKEND,
        metavar="BACKEND",
        help=(
            "So afeta a vetorizacao: com Ollama de pe (auto/local) o item "
            "ganha embedding para busca semantica; senao fica so o texto "
            "(busca TF-IDF). Nunca chama o Claude aqui."
        ),
    )

    recall_parser = subparsers.add_parser(
        "recall",
        help="Busca por similaridade na memoria local da Athena.",
    )
    recall_parser.add_argument(
        "consulta",
        help="Pergunta/termos a rechamar da memoria.",
    )
    recall_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Pasta do projeto dona da memoria (padrao: atual).",
    )
    recall_parser.add_argument(
        "--k",
        type=int,
        default=MEMORY_DEFAULT_TOP_K,
        metavar="N",
        help=f"Quantos resultados mostrar (padrao: {MEMORY_DEFAULT_TOP_K}).",
    )
    recall_parser.add_argument(
        "--backend",
        choices=["auto", "local", "claude"],
        default=DEFAULT_BACKEND,
        metavar="BACKEND",
        help=(
            "Com Ollama de pe usa busca vetorial (cosseno); senao cai "
            "para TF-IDF puro. Deterministico e offline nos dois casos."
        ),
    )

    return parser.parse_args()


def _print_tip_gitignore(project_root: Path) -> None:

    gitignore = project_root / ".gitignore"

    if gitignore.exists():
        text = gitignore.read_text(encoding="utf-8", errors="replace")
        if OUTPUT_DIRNAME in text:
            return

    print(
        f"\n[TIP] Considere adicionar \"{OUTPUT_DIRNAME}/\" ao "
        ".gitignore deste projeto, para nao versionar os resumos "
        "gerados pela Athena."
    )


def run_index(args: argparse.Namespace) -> None:

    # So exige o CLI do Claude quando o backend resolvido realmente o
    # usa. Com --backend local (ou auto com Ollama de pe), o Claude nao
    # e necessario e nada deve falhar por ele estar ausente. Em
    # --dry-run nao ha chamada alguma, entao nem se faz o probe de
    # disponibilidade (mantem o dry-run 100% offline e deterministico).
    if not args.dry_run:
        resolved_backend = resolve_backend(args.backend)

        if resolved_backend == "claude" and not command_exists("claude"):
            print(
                "[ERROR] Nenhum backend disponivel: Ollama local nao "
                "esta de pe e o Claude Code (\"claude\") nao foi "
                "encontrado. Suba o Ollama, instale/authentique o "
                "Claude Code, ou rode --dry-run."
            )
            sys.exit(1)

    project_root = Path(args.path).resolve()

    if not project_root.is_dir():
        print(
            f"[ERROR] Pasta nao encontrada: {project_root}"
        )
        sys.exit(1)

    output_dir = project_root / OUTPUT_DIRNAME
    tree_dir = output_dir / TREE_DIRNAME

    athenaignore = project_root / ATHENAIGNORE_FILENAME
    matcher = build_matcher(
        project_root,
        athenaignore if athenaignore.exists() else None,
    )

    tree = build_tree(project_root, project_root, matcher)
    total = count_files(tree)

    print("=" * 70)
    print(f"Athena — indexando: {project_root}")
    print("=" * 70)
    print(f"Arquivos encontrados (apos ignore rules): {total}")

    if total > args.max_files:
        print(
            f"\n[ERROR] {total} arquivos excede o limite de "
            f"seguranca de {args.max_files}."
        )
        print(
            "[ERROR] Rode de novo com --max-files "
            f"{total} (ou maior) se isso for esperado."
        )
        sys.exit(1)

    if total == 0:

        print("\n[INFO] Nenhum arquivo para indexar.")

        if args.dry_run:
            print(
                "[DRY-RUN] Nenhum indice seria escrito em disco."
            )
            return

        # Projeto vazio (ex.: pasta recem-criada) ainda e um estado
        # valido de indice, nao um erro: escreve um resumo raiz
        # minimo em vez de deixar .athena/summary.atn.md ausente, pra
        # quem consome o indice (ex.: Zeus) nao tratar "sem arquivos"
        # como "indexacao falhou".
        output_dir.mkdir(parents=True, exist_ok=True)

        (output_dir / ROOT_SUMMARY_FILENAME).write_text(
            "Projeto vazio: nenhum arquivo encontrado para indexar "
            "(apos ignore rules).\n",
            encoding="utf-8",
        )

        Manifest(output_dir / "manifest.json").save()

        hide_windows_path(output_dir)

        print(f"[OK] Indice (vazio) salvo em: {output_dir}")

        return

    if args.dry_run:
        print("\n[DRY-RUN] Nenhuma chamada ao Claude sera feita.\n")

    manifest = Manifest(output_dir / "manifest.json")
    stats = IndexStats()

    # "" pede explicitamente o modelo padrao da sessao do Claude Code
    # (sem "--model" repassado pro comando).
    model = args.model or None

    file_summaries = summarize_files_parallel(
        tree,
        manifest,
        tree_dir,
        force=args.force,
        dry_run=args.dry_run,
        stats=stats,
        max_workers=args.workers,
        model=model,
        backend=args.backend,
    )

    root_summary = summarize_dir(
        tree,
        manifest,
        tree_dir,
        force=args.force,
        dry_run=args.dry_run,
        stats=stats,
        file_summaries=file_summaries,
        model=model,
        backend=args.backend,
    )

    print()
    print("=" * 70)
    print("Resumo da execução")
    print("=" * 70)
    print(f"Arquivos resumidos agora:   {stats.files_summarized}")
    print(f"Arquivos reaproveitados:    {stats.files_skipped_cache}")
    print(f"Arquivos binarios pulados:  {stats.files_skipped_binary}")
    print(f"Pastas resumidas agora:     {stats.dirs_summarized}")
    print(f"Pastas reaproveitadas:      {stats.dirs_skipped_cache}")
    print(f"Erros:                      {stats.errors}")

    if args.dry_run:
        print(
            "\n[DRY-RUN] Nada foi escrito em disco. Rode sem "
            "--dry-run para gerar os resumos de verdade."
        )
        return

    stale_entries = manifest.prune_untouched()

    for entry in stale_entries:
        summary_path = tree_dir / entry["summary_path"]
        if summary_path.exists():
            summary_path.unlink()

    if stale_entries:
        print(
            f"\n[INFO] {len(stale_entries)} resumo(s) orfao(s) "
            "removido(s) (arquivo/pasta nao existe mais)."
        )

    manifest.save()

    if root_summary is not None:
        (output_dir / ROOT_SUMMARY_FILENAME).write_text(
            root_summary.strip() + "\n",
            encoding="utf-8",
        )

    hide_windows_path(output_dir)

    print(f"\n[OK] Indice salvo em: {output_dir}")
    print(f"[OK] Resumo raiz:      {output_dir / ROOT_SUMMARY_FILENAME}")

    _print_tip_gitignore(project_root)


def run_show(args: argparse.Namespace) -> None:

    project_root = Path(args.path).resolve()
    output_dir = project_root / OUTPUT_DIRNAME
    tree_dir = output_dir / TREE_DIRNAME

    target = args.target.strip().strip("/")

    if target in (".", ""):
        summary_path = output_dir / ROOT_SUMMARY_FILENAME
    else:
        dir_summary_path = tree_dir / target / f"_dir_summary{SUMMARY_EXTENSION}"
        file_summary_path = tree_dir / f"{target}{SUMMARY_EXTENSION}"

        if dir_summary_path.exists():
            summary_path = dir_summary_path
        else:
            summary_path = file_summary_path

    if not summary_path.exists():
        print(
            f"[ERROR] Nenhum resumo encontrado para "
            f"'{args.target}'."
        )
        print(
            "[ERROR] Rode \"athena.py index\" primeiro, ou "
            "confira o caminho."
        )
        sys.exit(1)

    print(
        summary_path.read_text(encoding="utf-8", errors="replace")
    )


def _memory_embed_fn(backend_arg: str):
    """
    Devolve ``ollama_embed`` só quando o backend resolvido é local (Ollama
    de pé); caso contrário ``None``, o que faz a busca cair no fallback
    TF-IDF puro. Nenhum caminho aqui chama o Claude: memória é 100%
    local por decisão de privacidade.
    """

    if resolve_backend(backend_arg) == "local":
        return ollama_client.ollama_embed

    return None


def run_remember(args: argparse.Namespace) -> None:

    project_root = Path(args.path).resolve()
    file_path = Path(args.arquivo)

    if not file_path.is_absolute():
        file_path = project_root / file_path

    if not file_path.is_file():
        print(f"[ERROR] Arquivo nao encontrado: {file_path}")
        sys.exit(1)

    text = file_path.read_text(encoding="utf-8", errors="replace").strip()

    if not text:
        print("[ERROR] Arquivo vazio: nada para guardar na memoria.")
        sys.exit(1)

    try:
        source_display = str(file_path.relative_to(project_root))
    except ValueError:
        source_display = str(file_path)

    store = MemoryStore.for_project(project_root)
    try:
        embed_fn = _memory_embed_fn(args.backend)
        embedding = embed_fn(text) if embed_fn is not None else None
        item_id = store.add(
            args.kind, text, source_path=source_display, embedding=embedding
        )
    finally:
        store.close()

    vectorized = "com" if embedding else "sem"
    print(
        f"[OK] memoria #{item_id} ({args.kind}, {vectorized} embedding) "
        f"<- {source_display}"
    )


def run_recall(args: argparse.Namespace) -> None:

    project_root = Path(args.path).resolve()

    store = MemoryStore.for_project(project_root)
    try:
        if store.count() == 0:
            print(
                "[INFO] Memoria vazia. Use \"athena.py remember <kind> "
                "<arquivo>\" para indexar decisoes/convencoes."
            )
            return

        embed_fn = _memory_embed_fn(args.backend)
        results = store.search(args.consulta, k=args.k, embed_fn=embed_fn)
    finally:
        store.close()

    if not results:
        print(f"[INFO] Nenhum resultado para: {args.consulta}")
        return

    mode = "cosseno" if embed_fn is not None else "tf-idf"
    print(f"Resultados ({mode}) para: {args.consulta}")

    for item, score in results:
        location = item.source_path or "(sem fonte)"
        preview = item.text.strip().splitlines()[0] if item.text.strip() else ""
        print(f"- [{score:.3f}] ({item.kind}) {location}")
        if preview:
            print(f"    {preview}")


def main() -> None:

    args = parse_args()

    if args.command == "index":
        run_index(args)
    elif args.command == "show":
        run_show(args)
    elif args.command == "remember":
        run_remember(args)
    elif args.command == "recall":
        run_recall(args)
    else:
        print(
            "Uso: python athena.py {index,show,remember,recall} ... "
            "(--help para detalhes)"
        )
        sys.exit(1)
