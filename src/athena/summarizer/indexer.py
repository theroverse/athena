from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from athena.hashing import hash_text
from athena.ignore import IgnoreMatcher
from athena.manifest import Manifest
from athena.settings import MAX_FILE_CHARS, SUMMARY_EXTENSION
from athena.summarizer.claude_client import call_claude
from athena.summarizer.prompts import FILE_SUMMARY_PROMPT, FOLDER_SUMMARY_PROMPT


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


def build_tree(
    directory: Path,
    root: Path,
    matcher: IgnoreMatcher,
) -> DirNode:

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
        rel = _relative_posix(entry_path, root)

        if matcher.is_ignored(rel, is_dir):
            continue

        if is_dir:
            node.subdirs.append(
                build_tree(entry_path, root, matcher)
            )
        else:
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
) -> str | None:

    content = _read_text_or_none(file_node.absolute_path)

    if content is None:
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
        stats.files_summarized += 1
        print(f"[DRY-RUN] Resumiria arquivo: {file_node.relative_path}")
        return "[dry-run] resumo seria gerado aqui"

    prompt = FILE_SUMMARY_PROMPT.format(
        relative_path=file_node.relative_path,
        content=content,
    )

    summary = call_claude(prompt)

    if summary is None:
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

    manifest.mark(
        file_node.relative_path,
        content_hash,
        summary_rel_path,
        "file",
    )

    stats.files_summarized += 1

    print(f"[OK] Resumido: {file_node.relative_path}")

    return summary


def summarize_dir(
    dir_node: DirNode,
    manifest: Manifest,
    tree_dir: Path,
    *,
    force: bool,
    dry_run: bool,
    stats: IndexStats,
) -> str | None:

    children_summaries: list[tuple[str, str]] = []

    for subdir in dir_node.subdirs:

        summary = summarize_dir(
            subdir,
            manifest,
            tree_dir,
            force=force,
            dry_run=dry_run,
            stats=stats,
        )

        if summary is not None:
            children_summaries.append(
                (subdir.relative_path + "/", summary)
            )

    for file_node in dir_node.files:

        summary = summarize_file(
            file_node,
            manifest,
            tree_dir,
            force=force,
            dry_run=dry_run,
            stats=stats,
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

    summary = call_claude(prompt)

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
