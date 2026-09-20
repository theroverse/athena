from __future__ import annotations

import argparse
import sys
from pathlib import Path

from athena.ignore import build_matcher
from athena.manifest import Manifest
from athena.settings import (
    ATHENAIGNORE_FILENAME,
    DEFAULT_MAX_FILES,
    OUTPUT_DIRNAME,
    ROOT_SUMMARY_FILENAME,
    SUMMARY_EXTENSION,
    TREE_DIRNAME,
)
from athena.summarizer.indexer import (
    IndexStats,
    build_tree,
    count_files,
    summarize_dir,
)
from athena.system.process import command_exists

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
    -h, --help         Mostra esta ajuda e sai, sem indexar nada e
                       sem chamar o Claude.

COMO FUNCIONA
    A Athena resume cada arquivo do projeto usando o Claude Code
    ("claude -p"), de baixo para cima: primeiro cada arquivo, depois
    cada pasta (a partir dos resumos dos seus arquivos/subpastas),
    ate chegar num resumo da raiz do projeto. Cada resumo fica em
    .athena/tree/<caminho>.md (arquivos) ou
    .athena/tree/<caminho>/_dir_summary.md (pastas), espelhando a
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

EXEMPLOS
    python athena.py index
    python athena.py index --dry-run
    python athena.py index /caminho/do/projeto
    python athena.py index --force
    python athena.py index --max-files 1000
    python athena.py show src/components/Button.tsx
    python athena.py show src/components
    python athena.py show .
    python athena.py --help
"""


def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        prog="athena.py",
        description=(
            "Indexador recursivo de resumos de projeto para uso "
            "como contexto de IA (via Claude Code)."
        ),
        epilog=HELP_EPILOG % DEFAULT_MAX_FILES,
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

    if not command_exists("claude") and not args.dry_run:
        print(
            "[ERROR] Claude Code executable was not found."
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
        return

    if args.dry_run:
        print("\n[DRY-RUN] Nenhuma chamada ao Claude sera feita.\n")

    manifest = Manifest(output_dir / "manifest.json")
    stats = IndexStats()

    root_summary = summarize_dir(
        tree,
        manifest,
        tree_dir,
        force=args.force,
        dry_run=args.dry_run,
        stats=stats,
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
        dir_summary_path = tree_dir / target / "_dir_summary.md"
        file_summary_path = tree_dir / f"{target}.md"

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


def main() -> None:

    args = parse_args()

    if args.command == "index":
        run_index(args)
    elif args.command == "show":
        run_show(args)
    else:
        print(
            "Uso: python athena.py {index,show} ... "
            "(--help para detalhes)"
        )
        sys.exit(1)
