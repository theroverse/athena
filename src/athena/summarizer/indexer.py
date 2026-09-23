from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from athena.hashing import hash_text
from athena.ignore import IgnoreMatcher
from athena.manifest import Manifest
from athena.settings import (
    ALWAYS_IGNORED_NAMES,
    DEFAULT_BACKEND,
    MAX_FILE_CHARS,
    SUMMARY_EXTENSION,
)
from athena.summarizer import backend as backend_router
from athena.summarizer.prompts import FILE_SUMMARY_PROMPT, FOLDER_SUMMARY_PROMPT

_stats_lock = threading.Lock()


@dataclass
class FileNode:
    relative_path: str
    absolute_path: Path


@dataclass
class DirNode:
    relative_path: str
    absolute_path: Path
    files: list[FileNode] = field(default_factory=list)
    subdirs: list["DirNode"] = field(default_factory=list)


@dataclass
class IndexStats:
    files_summarized: int = 0
    files_skipped_cache: int = 0
    files_skipped_binary: int = 0
    dirs_summarized: int = 0
    dirs_skipped_cache: int = 0
    dirs_skipped_empty: int = 0
    errors: int = 0


def _relative_posix(path: Path, root: Path) -> str:
    rel = path.relative_to(root)
    text = rel.as_posix()
    return text if text else "."


def _is_ignored_by_layers(
    entry_path: Path,
    layers: list[tuple[Path, IgnoreMatcher]],
    is_dir: bool,
) -> bool:

    if entry_path.name in ALWAYS_IGNORED_NAMES:
        return True

    ignored = False

    for base, layer_matcher in layers:
        rel = _relative_posix(entry_path, base)
        verdict = layer_matcher.match_rules(rel, is_dir)
        if verdict is not None:
            ignored = verdict

    return ignored


def build_tree(
    directory: Path,
    root: Path,
    matcher: IgnoreMatcher,
    _layers: list[tuple[Path, IgnoreMatcher]] | None = None,
) -> DirNode:
    """
    A pasta raiz ja carrega seu proprio .gitignore/.athenaignore via
    `matcher` (ver `build_matcher`). Cada subpasta que tambem tenha um
    .gitignore proprio empilha uma camada extra, igual ao git real:
    regras de niveis mais profundos so sobrepoem as de niveis acima
    quando realmente casam com o caminho (ver `_is_ignored_by_layers`).
    Isso evita ter que listar manualmente node_modules/dist/etc de cada
    submodulo num .gitignore/.athenaignore central na raiz.
    """

    if _layers is None:
        _layers = [(root, matcher)]

    own_gitignore = directory / ".gitignore"

    if directory != root and own_gitignore.is_file():
        nested_matcher = IgnoreMatcher()
        nested_matcher.load_file(own_gitignore)
        _layers = [*_layers, (directory, nested_matcher)]

    entries = sorted(
        os.scandir(directory),
        key=lambda entry: entry.name,
    )

    node = DirNode(
        relative_path=_relative_posix(directory, root),
        absolute_path=directory,
    )

    for entry in entries:

        entry_path = Path(entry.path)
        is_dir = entry.is_dir(follow_symlinks=False)

        if _is_ignored_by_layers(entry_path, _layers, is_dir):
            continue

        if is_dir:
            node.subdirs.append(
                build_tree(entry_path, root, matcher, _layers)
            )
        else:
            rel = _relative_posix(entry_path, root)
            node.files.append(
                FileNode(relative_path=rel, absolute_path=entry_path)
            )

    return node


def count_files(node: DirNode) -> int:

    total = len(node.files)

    for subdir in node.subdirs:
        total += count_files(subdir)

    return total


def _read_text_or_none(path: Path) -> str | None:

    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def _summary_path_for_file(relative_path: str) -> str:
    return f"{relative_path}{SUMMARY_EXTENSION}"


def _summary_path_for_dir(relative_path: str) -> str:

    if relative_path == ".":
        return f"_dir_summary{SUMMARY_EXTENSION}"

    return f"{relative_path}/_dir_summary{SUMMARY_EXTENSION}"


def summarize_file(
    file_node: FileNode,
    manifest: Manifest,
    tree_dir: Path,
    *,
    force: bool,
    dry_run: bool,
    stats: IndexStats,
    model: str | None = None,
    backend: str = DEFAULT_BACKEND,
) -> str | None:
    """
    Pode ser chamada em paralelo (uma thread por arquivo, ver
    `summarize_files_parallel`) porque cada chamada le/escreve um
    `summary_abs_path` proprio (sem colisao entre arquivos) e a unica
    chamada real e a `call_claude`, que e I/O (subprocess), nao CPU —
    varias em paralelo aceleram o indexador sem competir por GIL.
    Mutacoes de `manifest`/`stats` (estado compartilhado entre
    threads) ficam atras de `_stats_lock`.
    """

    content = _read_text_or_none(file_node.absolute_path)

    if content is None:
        with _stats_lock:
            stats.files_skipped_binary += 1
        return None

    if len(content) > MAX_FILE_CHARS:
        content = (
            content[:MAX_FILE_CHARS]
            + "\n\n[... truncado, arquivo maior que o limite ...]"
        )

    content_hash = hash_text(content)
    summary_rel_path = _summary_path_for_file(file_node.relative_path)
    summary_abs_path = tree_dir / summary_rel_path

    cached_hash = manifest.get_hash(file_node.relative_path)

    if (
        not force
        and cached_hash == content_hash
        and summary_abs_path.exists()
    ):
        with _stats_lock:
            stats.files_skipped_cache += 1
            manifest.mark(
                file_node.relative_path,
                content_hash,
                summary_rel_path,
                "file",
            )
        return summary_abs_path.read_text(
            encoding="utf-8",
            errors="replace",
        )

    if dry_run:
        with _stats_lock:
            stats.files_summarized += 1
        print(f"[DRY-RUN] Resumiria arquivo: {file_node.relative_path}")
        return "[dry-run] resumo seria gerado aqui"

    prompt = FILE_SUMMARY_PROMPT.format(
        relative_path=file_node.relative_path,
        content=content,
    )

    summary = backend_router.summarize(prompt, backend=backend, model=model)

    if summary is None:
        with _stats_lock:
            stats.errors += 1
        print(
            f"[WARN] Falha ao resumir: {file_node.relative_path}"
        )
        return None

    summary_abs_path.parent.mkdir(parents=True, exist_ok=True)
    summary_abs_path.write_text(
        summary.strip() + "\n",
        encoding="utf-8",
    )

    with _stats_lock:
        manifest.mark(
            file_node.relative_path,
            content_hash,
            summary_rel_path,
            "file",
        )
        stats.files_summarized += 1

    print(f"[OK] Resumido: {file_node.relative_path}")

    return summary


def iter_files(dir_node: DirNode) -> Iterator[FileNode]:

    yield from dir_node.files

    for subdir in dir_node.subdirs:
        yield from iter_files(subdir)


def summarize_files_parallel(
    dir_node: DirNode,
    manifest: Manifest,
    tree_dir: Path,
    *,
    force: bool,
    dry_run: bool,
    stats: IndexStats,
    max_workers: int,
    model: str | None = None,
    backend: str = DEFAULT_BACKEND,
) -> dict[str, str]:
    """
    Resume todos os arquivos da arvore em paralelo (thread pool), antes
    do passo bottom-up de `summarize_dir`. Arquivos nao dependem uns
    dos outros (so pastas dependem dos resumos dos filhos), e e ai que
    o indexador gasta a maior parte do tempo — uma chamada real ao
    Claude (subprocess, I/O-bound) por arquivo nao cacheado.
    """

    file_nodes = list(iter_files(dir_node))
    results: dict[str, str] = {}

    if not file_nodes:
        return results

    if max_workers <= 1:
        for file_node in file_nodes:
            summary = summarize_file(
                file_node,
                manifest,
                tree_dir,
                force=force,
                dry_run=dry_run,
                stats=stats,
                model=model,
                backend=backend,
            )
            if summary is not None:
                results[file_node.relative_path] = summary
        return results

    with ThreadPoolExecutor(max_workers=max_workers) as executor:

        future_to_node = {
            executor.submit(
                summarize_file,
                file_node,
                manifest,
                tree_dir,
                force=force,
                dry_run=dry_run,
                stats=stats,
                model=model,
                backend=backend,
            ): file_node
            for file_node in file_nodes
        }

        for future in as_completed(future_to_node):
            file_node = future_to_node[future]
            summary = future.result()
            if summary is not None:
                results[file_node.relative_path] = summary

    return results


def summarize_dir(
    dir_node: DirNode,
    manifest: Manifest,
    tree_dir: Path,
    *,
    force: bool,
    dry_run: bool,
    stats: IndexStats,
    file_summaries: dict[str, str] | None = None,
    model: str | None = None,
    backend: str = DEFAULT_BACKEND,
) -> str | None:
    """
    `file_summaries` (opcional): resumos de arquivo ja calculados (ver
    `summarize_files_parallel`), consultados por caminho em vez de
    chamar `summarize_file` de novo aqui. Sem isso (None), resume cada
    arquivo diretamente e sequencialmente — mesmo comportamento de
    antes desta funcao existir, usado quando chamar `summarize_dir`
    isoladamente (ex.: testes, ou uma arvore pequena que nao compensa
    paralelizar).
    """

    children_summaries: list[tuple[str, str]] = []

    for subdir in dir_node.subdirs:

        summary = summarize_dir(
            subdir,
            manifest,
            tree_dir,
            force=force,
            dry_run=dry_run,
            stats=stats,
            file_summaries=file_summaries,
            model=model,
            backend=backend,
        )

        if summary is not None:
            children_summaries.append(
                (subdir.relative_path + "/", summary)
            )

    for file_node in dir_node.files:

        if file_summaries is not None:
            summary = file_summaries.get(file_node.relative_path)
        else:
            summary = summarize_file(
                file_node,
                manifest,
                tree_dir,
                force=force,
                dry_run=dry_run,
                stats=stats,
                model=model,
                backend=backend,
            )

        if summary is not None:
            children_summaries.append(
                (file_node.relative_path, summary)
            )

    if not children_summaries:
        stats.dirs_skipped_empty += 1
        return None

    composite_source = "\n".join(
        f"{name}:{hash_text(summary)}"
        for name, summary in sorted(children_summaries)
    )
    composite_hash = hash_text(composite_source)

    summary_rel_path = _summary_path_for_dir(dir_node.relative_path)
    summary_abs_path = tree_dir / summary_rel_path

    manifest_key = dir_node.relative_path
    cached_hash = manifest.get_hash(manifest_key)

    if (
        not force
        and cached_hash == composite_hash
        and summary_abs_path.exists()
    ):
        stats.dirs_skipped_cache += 1
        manifest.mark(manifest_key, composite_hash, summary_rel_path, "dir")
        return summary_abs_path.read_text(
            encoding="utf-8",
            errors="replace",
        )

    if dry_run:
        stats.dirs_summarized += 1
        print(f"[DRY-RUN] Resumiria pasta: {dir_node.relative_path}")
        return "[dry-run] resumo de pasta seria gerado aqui"

    children_block = "\n\n".join(
        f"### {name}\n\n{summary}"
        for name, summary in children_summaries
    )

    prompt = FOLDER_SUMMARY_PROMPT.format(
        relative_path=dir_node.relative_path,
        children=children_block,
    )

    summary = backend_router.summarize(prompt, backend=backend, model=model)

    if summary is None:
        stats.errors += 1
        print(
            f"[WARN] Falha ao resumir pasta: {dir_node.relative_path}"
        )
        return None

    summary_abs_path.parent.mkdir(parents=True, exist_ok=True)
    summary_abs_path.write_text(
        summary.strip() + "\n",
        encoding="utf-8",
    )

    manifest.mark(manifest_key, composite_hash, summary_rel_path, "dir")

    stats.dirs_summarized += 1

    print(f"[OK] Resumida pasta: {dir_node.relative_path}")

    return summary
