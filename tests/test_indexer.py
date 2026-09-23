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
    iter_files,
    summarize_dir,
    summarize_file,
    summarize_files_parallel,
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


def test_build_tree_respects_nested_gitignore_in_subdir(tmp_path):
    project = _project(tmp_path)
    write_tree(
        project,
        {
            "packages/app/node_modules/dep.js": "x",
            "packages/app/src/main.py": "y",
            "packages/app/.gitignore": "node_modules\n",
        },
    )

    tree = build_tree(project, project, IgnoreMatcher())

    app_dir = tree.subdirs[0].subdirs[0]
    assert app_dir.relative_path == "packages/app"
    assert [d.relative_path for d in app_dir.subdirs] == ["packages/app/src"]


def test_build_tree_nested_gitignore_does_not_affect_siblings(tmp_path):
    project = _project(tmp_path)
    write_tree(
        project,
        {
            "pkg-a/node_modules/dep.js": "x",
            "pkg-a/.gitignore": "node_modules\n",
            "pkg-b/node_modules/dep.js": "y",
        },
    )

    tree = build_tree(project, project, IgnoreMatcher())

    by_name = {d.relative_path: d for d in tree.subdirs}
    assert [d.relative_path for d in by_name["pkg-a"].subdirs] == []
    assert [d.relative_path for d in by_name["pkg-b"].subdirs] == [
        "pkg-b/node_modules"
    ]


def test_build_tree_root_gitignore_not_loaded_twice_via_layers(tmp_path):
    project = _project(tmp_path)
    write_tree(project, {"keep.py": "x", "skip.log": "y"})
    matcher = IgnoreMatcher()
    matcher.add_line("*.log")

    # The root's own .gitignore is already folded into `matcher` by
    # build_matcher(); build_tree must not double-apply it as a nested
    # layer when directory == root.
    tree = build_tree(project, project, matcher)

    assert [f.relative_path for f in tree.files] == ["keep.py"]


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

    with patch("athena.summarizer.indexer.backend_router.summarize") as mock_claude:
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
    with patch("athena.summarizer.indexer.backend_router.summarize") as mock_claude:
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
        "athena.summarizer.indexer.backend_router.summarize", return_value="fresh summary"
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

    with patch("athena.summarizer.indexer.backend_router.summarize") as mock_claude:
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
        "athena.summarizer.indexer.backend_router.summarize", side_effect=fake_call_claude
    ):
        summarize_file(
            node, manifest, tmp_path / "tree", force=False, dry_run=False, stats=stats
        )

    assert "[... truncado, arquivo maior que o limite ...]" in captured_prompt["value"]


def test_summarize_file_claude_failure_returns_none_and_counts_error(tmp_path):
    node = make_file_node(tmp_path, "a.py", "print(1)")
    manifest = Manifest(tmp_path / "manifest.json")
    stats = IndexStats()

    with patch("athena.summarizer.indexer.backend_router.summarize", return_value=None):
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
        "athena.summarizer.indexer.backend_router.summarize", return_value="  the summary  "
    ):
        result = summarize_file(
            node, manifest, tree_dir, force=False, dry_run=False, stats=stats
        )

    assert result == "  the summary  "
    assert (tree_dir / "a.py.atn.md").read_text(encoding="utf-8") == "the summary\n"
    assert manifest.get_hash("a.py") == hash_text("print(1)")
    assert stats.files_summarized == 1


def test_summarize_file_forwards_model_to_call_claude(tmp_path):
    tree_dir = tmp_path / "tree"
    node = make_file_node(tmp_path, "a.py", "print(1)")
    manifest = Manifest(tmp_path / "manifest.json")
    stats = IndexStats()

    with patch(
        "athena.summarizer.indexer.backend_router.summarize", return_value="summary"
    ) as mock_claude:
        summarize_file(
            node,
            manifest,
            tree_dir,
            force=False,
            dry_run=False,
            stats=stats,
            model="haiku",
        )

    assert mock_claude.call_args.kwargs["model"] == "haiku"


# ---------------------------------------------------------------------------
# iter_files / summarize_files_parallel
# ---------------------------------------------------------------------------


def test_iter_files_flattens_whole_tree(tmp_path):
    project = tmp_path / "project"
    write_tree(
        project,
        {"a.py": "x", "sub/b.py": "y", "sub/deep/c.py": "z"},
    )

    tree = build_tree(project, project, IgnoreMatcher())

    paths = sorted(f.relative_path for f in iter_files(tree))
    assert paths == ["a.py", "sub/b.py", "sub/deep/c.py"]


def test_summarize_files_parallel_empty_tree_returns_empty_dict(tmp_path):
    node = DirNode(relative_path=".", absolute_path=tmp_path)
    manifest = Manifest(tmp_path / "manifest.json")
    stats = IndexStats()

    with patch("athena.summarizer.indexer.backend_router.summarize") as mock_claude:
        result = summarize_files_parallel(
            node,
            manifest,
            tmp_path / "tree",
            force=False,
            dry_run=False,
            stats=stats,
            max_workers=4,
        )

    assert result == {}
    mock_claude.assert_not_called()


def test_summarize_files_parallel_sequential_matches_parallel_results(tmp_path):
    project = tmp_path / "project"
    write_tree(project, {"a.py": "print(1)", "sub/b.py": "print(2)"})
    tree = build_tree(project, project, IgnoreMatcher())

    def fake_call_claude(prompt, **kwargs):
        return f"summary for {prompt[:0]}"  # dummy, content not asserted

    for workers in (1, 4):
        manifest = Manifest(tmp_path / f"manifest_{workers}.json")
        stats = IndexStats()
        tree_dir = tmp_path / f"tree_{workers}"

        with patch(
            "athena.summarizer.indexer.backend_router.summarize",
            side_effect=fake_call_claude,
        ):
            result = summarize_files_parallel(
                tree,
                manifest,
                tree_dir,
                force=False,
                dry_run=False,
                stats=stats,
                max_workers=workers,
            )

        assert set(result.keys()) == {"a.py", "sub/b.py"}
        assert stats.files_summarized == 2
        assert stats.errors == 0


def test_summarize_files_parallel_forwards_model(tmp_path):
    project = tmp_path / "project"
    write_tree(project, {"a.py": "print(1)", "b.py": "print(2)"})
    tree = build_tree(project, project, IgnoreMatcher())
    manifest = Manifest(tmp_path / "manifest.json")
    stats = IndexStats()

    with patch(
        "athena.summarizer.indexer.backend_router.summarize", return_value="summary"
    ) as mock_claude:
        summarize_files_parallel(
            tree,
            manifest,
            tmp_path / "tree",
            force=False,
            dry_run=False,
            stats=stats,
            max_workers=4,
            model="haiku",
        )

    assert mock_claude.call_count == 2
    for call in mock_claude.call_args_list:
        assert call.kwargs["model"] == "haiku"


def test_summarize_files_parallel_stats_not_corrupted_under_concurrency(tmp_path):
    # Regression: stats.files_summarized/errors are shared counters
    # mutated from worker threads; without _stats_lock, concurrent
    # "+=" updates can lose increments (CPython does not make that
    # atomic across bytecode-level context switches).
    project = tmp_path / "project"
    write_tree(project, {f"f{i}.py": f"x{i}" for i in range(20)})
    tree = build_tree(project, project, IgnoreMatcher())
    manifest = Manifest(tmp_path / "manifest.json")
    stats = IndexStats()

    with patch(
        "athena.summarizer.indexer.backend_router.summarize", return_value="summary"
    ):
        result = summarize_files_parallel(
            tree,
            manifest,
            tmp_path / "tree",
            force=False,
            dry_run=False,
            stats=stats,
            max_workers=8,
        )

    assert len(result) == 20
    assert stats.files_summarized == 20


# ---------------------------------------------------------------------------
# summarize_dir
# ---------------------------------------------------------------------------


def test_summarize_dir_empty_returns_none_without_calling_claude(tmp_path):
    node = DirNode(relative_path=".", absolute_path=tmp_path)
    manifest = Manifest(tmp_path / "manifest.json")
    stats = IndexStats()

    with patch("athena.summarizer.indexer.backend_router.summarize") as mock_claude:
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
        "athena.summarizer.indexer.backend_router.summarize", side_effect=fake_call_claude
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
        "athena.summarizer.indexer.backend_router.summarize", return_value="same summary"
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
        "athena.summarizer.indexer.backend_router.summarize", return_value="summary"
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
        "athena.summarizer.indexer.backend_router.summarize", return_value="summary"
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
    with patch("athena.summarizer.indexer.backend_router.summarize") as mock_claude3:
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

    with patch("athena.summarizer.indexer.backend_router.summarize") as mock_claude:
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
        "athena.summarizer.indexer.backend_router.summarize", side_effect=fake_call_claude
    ):
        result = summarize_dir(
            tree, manifest, tmp_path / "tree", force=False, dry_run=False, stats=stats
        )

    assert result is None
    assert stats.errors == 1


def test_summarize_dir_uses_precomputed_file_summaries_without_calling_summarize_file(
    tmp_path,
):
    project = _project(tmp_path)
    write_tree(project, {"a.py": "print(1)"})
    tree = build_tree(project, project, IgnoreMatcher())
    manifest = Manifest(tmp_path / "manifest.json")
    stats = IndexStats()

    with patch(
        "athena.summarizer.indexer.backend_router.summarize", return_value="dir summary"
    ) as mock_claude:
        result = summarize_dir(
            tree,
            manifest,
            tmp_path / "tree",
            force=False,
            dry_run=False,
            stats=stats,
            file_summaries={"a.py": "precomputed file summary"},
        )

    assert result == "dir summary"
    # call_claude was only hit for the folder summary, never for the file
    # (it came from file_summaries instead of a fresh summarize_file call).
    mock_claude.assert_called_once()
    assert "precomputed file summary" in mock_claude.call_args.args[0]
    assert stats.files_summarized == 0


def test_summarize_dir_missing_entry_in_file_summaries_is_skipped(tmp_path):
    project = _project(tmp_path)
    write_tree(project, {"a.py": "print(1)"})
    tree = build_tree(project, project, IgnoreMatcher())
    manifest = Manifest(tmp_path / "manifest.json")
    stats = IndexStats()

    with patch("athena.summarizer.indexer.backend_router.summarize") as mock_claude:
        result = summarize_dir(
            tree,
            manifest,
            tmp_path / "tree",
            force=False,
            dry_run=False,
            stats=stats,
            file_summaries={},
        )

    # a.py has no entry in file_summaries (e.g. it failed upstream), so
    # it contributes nothing; with no children, the dir itself is empty.
    assert result is None
    mock_claude.assert_not_called()
    assert stats.dirs_skipped_empty == 1


def test_summarize_dir_forwards_model_to_call_claude(tmp_path):
    project = _project(tmp_path)
    write_tree(project, {"a.py": "print(1)"})
    tree = build_tree(project, project, IgnoreMatcher())
    manifest = Manifest(tmp_path / "manifest.json")
    stats = IndexStats()

    with patch(
        "athena.summarizer.indexer.backend_router.summarize", return_value="summary"
    ) as mock_claude:
        summarize_dir(
            tree,
            manifest,
            tmp_path / "tree",
            force=False,
            dry_run=False,
            stats=stats,
            model="haiku",
        )

    for call in mock_claude.call_args_list:
        assert call.kwargs["model"] == "haiku"
