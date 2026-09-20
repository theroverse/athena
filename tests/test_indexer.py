from __future__ import annotations

from unittest.mock import patch

from athena.hashing import hash_text
from athena.ignore import IgnoreMatcher
from athena.manifest import Manifest
from athena.settings import MAX_FILE_CHARS
from athena.summarizer.indexer import (
    DirNode,
    FileNode,
    IndexStats,
    build_tree,
    count_files,
    summarize_dir,
    summarize_file,
)


def write_tree(root, layout):
    """layout: dict of relative path -> content (str) or None for dirs."""
    for rel_path, content in layout.items():
        full = root / rel_path
        if content is None:
            full.mkdir(parents=True, exist_ok=True)
        else:
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# build_tree / count_files
# ---------------------------------------------------------------------------


def _project(tmp_path):
    # A dedicated source subdir, isolated from anything else tmp_path
    # might hold (e.g. the fixture's own fake HOME), so build_tree scans
    # exactly the files the test wrote.
    project = tmp_path / "project"
    project.mkdir()
    return project


def test_build_tree_sorts_entries_and_collects_files(tmp_path):
    project = _project(tmp_path)
    write_tree(project, {"b.py": "b", "a.py": "a"})

    tree = build_tree(project, project, IgnoreMatcher())

    assert [f.relative_path for f in tree.files] == ["a.py", "b.py"]


def test_build_tree_respects_ignore_matcher(tmp_path):
    project = _project(tmp_path)
    write_tree(project, {"keep.py": "x", "skip.log": "y"})
    matcher = IgnoreMatcher()
    matcher.add_line("*.log")

    tree = build_tree(project, project, matcher)

    assert [f.relative_path for f in tree.files] == ["keep.py"]


def test_build_tree_skips_ignored_directory_entirely(tmp_path):
    project = _project(tmp_path)
    write_tree(project, {"src/a.py": "x", "node_modules": None})
    matcher = IgnoreMatcher()
    matcher.add_line("node_modules")

    tree = build_tree(project, project, matcher)

    assert [d.relative_path for d in tree.subdirs] == ["src"]


def test_build_tree_recurses_into_subdirectories(tmp_path):
    project = _project(tmp_path)
    write_tree(project, {"sub/deep/file.py": "x"})

    tree = build_tree(project, project, IgnoreMatcher())

    assert tree.subdirs[0].relative_path == "sub"
    assert tree.subdirs[0].subdirs[0].relative_path == "sub/deep"
    assert tree.subdirs[0].subdirs[0].files[0].relative_path == "sub/deep/file.py"


def test_count_files_sums_recursively(tmp_path):
    project = _project(tmp_path)
    write_tree(
        project,
        {"a.py": "x", "sub/b.py": "y", "sub/c.py": "z", "sub/deep/d.py": "w"},
    )

    tree = build_tree(project, project, IgnoreMatcher())

    assert count_files(tree) == 4


def test_count_files_empty_tree_is_zero(tmp_path):
    project = _project(tmp_path)
    tree = build_tree(project, project, IgnoreMatcher())

    assert count_files(tree) == 0


# ---------------------------------------------------------------------------
# summarize_file
# ---------------------------------------------------------------------------


def make_file_node(tmp_path, relative_path, content):
    absolute = tmp_path / relative_path
    absolute.parent.mkdir(parents=True, exist_ok=True)
    absolute.write_bytes(content) if isinstance(content, bytes) else absolute.write_text(
        content, encoding="utf-8"
    )
    return FileNode(relative_path=relative_path, absolute_path=absolute)


def test_summarize_file_skips_binary_without_calling_claude(tmp_path):
    node = make_file_node(tmp_path, "bin.dat", b"\xff\xfe\x00\x01")
    manifest = Manifest(tmp_path / "manifest.json")
    stats = IndexStats()

    with patch("athena.summarizer.indexer.call_claude") as mock_claude:
        result = summarize_file(
            node, manifest, tmp_path / "tree", force=False, dry_run=False, stats=stats
        )

    assert result is None
    assert stats.files_skipped_binary == 1
    mock_claude.assert_not_called()


def test_summarize_file_cache_hit_skips_claude(tmp_path):
    tree_dir = tmp_path / "tree"
    node = make_file_node(tmp_path, "a.py", "print(1)")
    content_hash = hash_text("print(1)")

    manifest = Manifest(tmp_path / "manifest.json")
    manifest.mark("a.py", content_hash, "a.py.atn.md", "file")
    (tree_dir / "a.py.atn.md").parent.mkdir(parents=True, exist_ok=True)
    (tree_dir / "a.py.atn.md").write_text("cached summary", encoding="utf-8")

    stats = IndexStats()
    with patch("athena.summarizer.indexer.call_claude") as mock_claude:
        result = summarize_file(
            node, manifest, tree_dir, force=False, dry_run=False, stats=stats
        )

    assert result == "cached summary"
    assert stats.files_skipped_cache == 1
    mock_claude.assert_not_called()


def test_summarize_file_force_ignores_cache(tmp_path):
    tree_dir = tmp_path / "tree"
    node = make_file_node(tmp_path, "a.py", "print(1)")
    content_hash = hash_text("print(1)")

    manifest = Manifest(tmp_path / "manifest.json")
    manifest.mark("a.py", content_hash, "a.py.atn.md", "file")
    (tree_dir / "a.py.atn.md").parent.mkdir(parents=True, exist_ok=True)
    (tree_dir / "a.py.atn.md").write_text("cached summary", encoding="utf-8")

    stats = IndexStats()
    with patch(
        "athena.summarizer.indexer.call_claude", return_value="fresh summary"
    ) as mock_claude:
        result = summarize_file(
            node, manifest, tree_dir, force=True, dry_run=False, stats=stats
        )

    assert result == "fresh summary"
    mock_claude.assert_called_once()
    assert stats.files_summarized == 1


def test_summarize_file_dry_run_does_not_call_claude_or_write(tmp_path):
    tree_dir = tmp_path / "tree"
    node = make_file_node(tmp_path, "a.py", "print(1)")
    manifest = Manifest(tmp_path / "manifest.json")
    stats = IndexStats()

    with patch("athena.summarizer.indexer.call_claude") as mock_claude:
        result = summarize_file(
            node, manifest, tree_dir, force=False, dry_run=True, stats=stats
        )

    assert result is not None
    mock_claude.assert_not_called()
    assert not (tree_dir / "a.py.atn.md").exists()
    assert stats.files_summarized == 1


def test_summarize_file_truncates_large_content(tmp_path):
    huge_content = "x" * (MAX_FILE_CHARS + 5000)
    node = make_file_node(tmp_path, "big.py", huge_content)
    manifest = Manifest(tmp_path / "manifest.json")
    stats = IndexStats()

    captured_prompt = {}

    def fake_call_claude(prompt, **kwargs):
        captured_prompt["value"] = prompt
        return "summary"

    with patch(
        "athena.summarizer.indexer.call_claude", side_effect=fake_call_claude
    ):
        summarize_file(
            node, manifest, tmp_path / "tree", force=False, dry_run=False, stats=stats
        )

    assert "[... truncado, arquivo maior que o limite ...]" in captured_prompt["value"]


def test_summarize_file_claude_failure_returns_none_and_counts_error(tmp_path):
    node = make_file_node(tmp_path, "a.py", "print(1)")
    manifest = Manifest(tmp_path / "manifest.json")
    stats = IndexStats()

    with patch("athena.summarizer.indexer.call_claude", return_value=None):
        result = summarize_file(
            node, manifest, tmp_path / "tree", force=False, dry_run=False, stats=stats
        )

    assert result is None
    assert stats.errors == 1


def test_summarize_file_success_writes_summary_and_marks_manifest(tmp_path):
    tree_dir = tmp_path / "tree"
    node = make_file_node(tmp_path, "a.py", "print(1)")
    manifest = Manifest(tmp_path / "manifest.json")
    stats = IndexStats()

    with patch(
        "athena.summarizer.indexer.call_claude", return_value="  the summary  "
    ):
        result = summarize_file(
            node, manifest, tree_dir, force=False, dry_run=False, stats=stats
        )

    assert result == "  the summary  "
    assert (tree_dir / "a.py.atn.md").read_text(encoding="utf-8") == "the summary\n"
    assert manifest.get_hash("a.py") == hash_text("print(1)")
    assert stats.files_summarized == 1


# ---------------------------------------------------------------------------
# summarize_dir
# ---------------------------------------------------------------------------


def test_summarize_dir_empty_returns_none_without_calling_claude(tmp_path):
    node = DirNode(relative_path=".", absolute_path=tmp_path)
    manifest = Manifest(tmp_path / "manifest.json")
    stats = IndexStats()

    with patch("athena.summarizer.indexer.call_claude") as mock_claude:
        result = summarize_dir(
            node, manifest, tmp_path / "tree", force=False, dry_run=False, stats=stats
        )

    assert result is None
    assert stats.dirs_skipped_empty == 1
    mock_claude.assert_not_called()


def test_summarize_dir_bottom_up_summarizes_children_before_parent(tmp_path):
    project = _project(tmp_path)
    write_tree(project, {"sub/a.py": "print(1)"})
    tree = build_tree(project, project, IgnoreMatcher())
    manifest = Manifest(tmp_path / "manifest.json")
    stats = IndexStats()

    order = []

    def fake_call_claude(prompt, **kwargs):
        if "sub/a.py" in prompt:
            order.append("file")
        else:
            order.append("dir")
        return "summary"

    with patch(
        "athena.summarizer.indexer.call_claude", side_effect=fake_call_claude
    ):
        result = summarize_dir(
            tree, manifest, tmp_path / "tree", force=False, dry_run=False, stats=stats
        )

    assert result == "summary"
    assert order[0] == "file"
    assert "dir" in order


def test_summarize_dir_composite_hash_stable_regardless_of_insertion_order(tmp_path):
    # Two trees with same children but built via different insertion order
    # (achieved by directly constructing DirNode) must hash identically,
    # since summarize_dir sorts children_summaries before hashing.
    tree_a = DirNode(relative_path=".", absolute_path=tmp_path)
    tree_a.files = [
        FileNode("a.py", tmp_path / "a.py"),
        FileNode("b.py", tmp_path / "b.py"),
    ]
    (tmp_path / "a.py").write_text("A", encoding="utf-8")
    (tmp_path / "b.py").write_text("B", encoding="utf-8")

    tree_b = DirNode(relative_path=".", absolute_path=tmp_path)
    tree_b.files = [
        FileNode("b.py", tmp_path / "b.py"),
        FileNode("a.py", tmp_path / "a.py"),
    ]

    manifest_a = Manifest(tmp_path / "manifest_a.json")
    manifest_b = Manifest(tmp_path / "manifest_b.json")
    stats = IndexStats()

    with patch(
        "athena.summarizer.indexer.call_claude", return_value="same summary"
    ):
        summarize_dir(
            tree_a, manifest_a, tmp_path / "tree_a",
            force=False, dry_run=False, stats=stats,
        )
        summarize_dir(
            tree_b, manifest_b, tmp_path / "tree_b",
            force=False, dry_run=False, stats=stats,
        )

    assert manifest_a.get_hash(".") == manifest_b.get_hash(".")


def test_summarize_dir_cache_hit_skips_claude(tmp_path):
    project = _project(tmp_path)
    write_tree(project, {"a.py": "print(1)"})
    tree_dir = tmp_path / "tree"

    manifest = Manifest(tmp_path / "manifest.json")

    with patch(
        "athena.summarizer.indexer.call_claude", return_value="summary"
    ):
        summarize_dir(
            build_tree(project, project, IgnoreMatcher()),
            manifest, tree_dir, force=False, dry_run=False, stats=IndexStats(),
        )

    # Round 2: the file hits its cache (content unchanged), but its
    # cached summary is re-read from disk with a trailing "\n" appended
    # by summarize_file's write step, while round 1 hashed the raw
    # in-memory value without it. That text mismatch means the dir's
    # composite hash still differs once here -> one extra dir rebuild.
    stats2 = IndexStats()
    with patch(
        "athena.summarizer.indexer.call_claude", return_value="summary"
    ) as mock_claude:
        result2 = summarize_dir(
            build_tree(project, project, IgnoreMatcher()),
            manifest, tree_dir, force=False, dry_run=False, stats=stats2,
        )

    assert result2 == "summary"
    mock_claude.assert_called_once()
    assert stats2.files_skipped_cache == 1
    assert stats2.dirs_summarized == 1

    # Round 3: now both the file and dir hashes are stable -> full cache hit.
    stats3 = IndexStats()
    with patch("athena.summarizer.indexer.call_claude") as mock_claude3:
        result3 = summarize_dir(
            build_tree(project, project, IgnoreMatcher()),
            manifest, tree_dir, force=False, dry_run=False, stats=stats3,
        )

    assert result3 == "summary\n"
    mock_claude3.assert_not_called()
    assert stats3.dirs_skipped_cache == 1
    assert stats3.files_skipped_cache == 1


def test_summarize_dir_dry_run_does_not_call_claude(tmp_path):
    project = _project(tmp_path)
    write_tree(project, {"a.py": "print(1)"})
    tree = build_tree(project, project, IgnoreMatcher())
    manifest = Manifest(tmp_path / "manifest.json")
    stats = IndexStats()

    with patch("athena.summarizer.indexer.call_claude") as mock_claude:
        result = summarize_dir(
            tree, manifest, tmp_path / "tree", force=False, dry_run=True, stats=stats
        )

    assert result is not None
    mock_claude.assert_not_called()


def test_summarize_dir_claude_failure_returns_none(tmp_path):
    project = _project(tmp_path)
    write_tree(project, {"a.py": "print(1)"})
    tree = build_tree(project, project, IgnoreMatcher())
    manifest = Manifest(tmp_path / "manifest.json")
    stats = IndexStats()

    def fake_call_claude(prompt, **kwargs):
        return None if "###" in prompt else "file summary"

    with patch(
        "athena.summarizer.indexer.call_claude", side_effect=fake_call_claude
    ):
        result = summarize_dir(
            tree, manifest, tmp_path / "tree", force=False, dry_run=False, stats=stats
        )

    assert result is None
    assert stats.errors == 1
