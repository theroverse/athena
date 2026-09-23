from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from athena.cli import (
    main,
    parse_args,
    run_index,
    run_recall,
    run_remember,
    run_show,
)
from athena.settings import (
    DEFAULT_BACKEND,
    DEFAULT_MAX_FILES,
    DEFAULT_SUMMARY_MODEL,
    DEFAULT_WORKERS,
)
from athena.summarizer.indexer import IndexStats


def set_argv(monkeypatch, *args):
    monkeypatch.setattr("sys.argv", ["athena.py", *args])


# ---------------------------------------------------------------------------
# parse_args
# ---------------------------------------------------------------------------


def test_parse_args_index_defaults(monkeypatch):
    set_argv(monkeypatch, "index")

    args = parse_args()

    assert args.command == "index"
    assert args.path == "."
    assert args.force is False
    assert args.dry_run is False
    assert args.max_files == DEFAULT_MAX_FILES
    assert args.workers == DEFAULT_WORKERS
    assert args.model == DEFAULT_SUMMARY_MODEL


def test_parse_args_index_with_flags(monkeypatch):
    set_argv(
        monkeypatch,
        "index",
        "/some/project",
        "--force",
        "--dry-run",
        "--max-files",
        "999",
        "--workers",
        "8",
        "--model",
        "sonnet",
    )

    args = parse_args()

    assert args.path == "/some/project"
    assert args.force is True
    assert args.dry_run is True
    assert args.max_files == 999
    assert args.workers == 8
    assert args.model == "sonnet"


def test_parse_args_show(monkeypatch):
    set_argv(monkeypatch, "show", "src/a.py", "/some/project")

    args = parse_args()

    assert args.command == "show"
    assert args.target == "src/a.py"
    assert args.path == "/some/project"


def test_parse_args_show_default_path(monkeypatch):
    set_argv(monkeypatch, "show", ".")

    args = parse_args()

    assert args.path == "."


def test_main_no_command_exits(monkeypatch):
    set_argv(monkeypatch)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1


def test_main_dispatches_to_run_index(monkeypatch, tmp_path):
    set_argv(monkeypatch, "index", str(tmp_path))

    with patch("athena.cli.run_index") as mock_run_index:
        main()

    mock_run_index.assert_called_once()


def test_main_dispatches_to_run_show(monkeypatch, tmp_path):
    set_argv(monkeypatch, "show", ".", str(tmp_path))

    with patch("athena.cli.run_show") as mock_run_show:
        main()

    mock_run_show.assert_called_once()


# ---------------------------------------------------------------------------
# run_index
# ---------------------------------------------------------------------------


def make_args(**overrides):
    defaults = dict(
        path=".",
        force=False,
        dry_run=False,
        max_files=DEFAULT_MAX_FILES,
        workers=DEFAULT_WORKERS,
        model=DEFAULT_SUMMARY_MODEL,
        backend=DEFAULT_BACKEND,
    )
    defaults.update(overrides)
    return MagicMock(**defaults)


def test_run_index_exits_when_claude_missing_and_not_dry_run(tmp_path):
    # Força backend="claude" para testar o gate de forma determinística,
    # sem depender de um Ollama local estar (ou não) de pé na máquina.
    args = make_args(path=str(tmp_path), backend="claude")

    with patch("athena.cli.command_exists", return_value=False):
        with pytest.raises(SystemExit) as exc_info:
            run_index(args)

    assert exc_info.value.code == 1


def test_run_index_dry_run_does_not_require_claude(tmp_path):
    args = make_args(path=str(tmp_path), dry_run=True)

    with patch("athena.cli.command_exists", return_value=False):
        # Should not exit due to missing claude, since dry_run bypasses it.
        run_index(args)

    assert not (tmp_path / ".athena").exists()


def test_run_index_exits_when_project_dir_missing(tmp_path):
    args = make_args(path=str(tmp_path / "nope"))

    with patch("athena.cli.command_exists", return_value=True):
        with pytest.raises(SystemExit) as exc_info:
            run_index(args)

    assert exc_info.value.code == 1


def test_run_index_exits_when_over_max_files(tmp_path):
    for i in range(5):
        (tmp_path / f"file{i}.py").write_text("x", encoding="utf-8")
    args = make_args(path=str(tmp_path), max_files=2)

    with patch("athena.cli.command_exists", return_value=True), patch(
        "athena.cli.summarize_dir"
    ) as mock_summarize:
        with pytest.raises(SystemExit) as exc_info:
            run_index(args)

    assert exc_info.value.code == 1
    mock_summarize.assert_not_called()


def test_run_index_zero_files_still_writes_a_minimal_index(tmp_path):
    # An empty project (e.g. a freshly created folder) is a valid index
    # state, not a failure: downstream consumers (e.g. Zeus) look for
    # .athena/summary.atn.md to exist and treat its absence as "indexing
    # never ran", so it must be written even with zero files.
    args = make_args(path=str(tmp_path))

    with patch("athena.cli.command_exists", return_value=True):
        run_index(args)

    assert (tmp_path / ".athena" / "manifest.json").exists()
    assert (tmp_path / ".athena" / "summary.atn.md").exists()


def test_run_index_zero_files_dry_run_writes_nothing(tmp_path):
    args = make_args(path=str(tmp_path), dry_run=True)

    with patch("athena.cli.command_exists", return_value=True):
        run_index(args)

    assert not (tmp_path / ".athena").exists()


def test_run_index_dry_run_writes_nothing_to_disk(tmp_path):
    (tmp_path / "a.py").write_text("print(1)", encoding="utf-8")
    args = make_args(path=str(tmp_path), dry_run=True)

    with patch("athena.cli.command_exists", return_value=True), patch(
        "athena.cli.summarize_dir", return_value="root summary"
    ) as mock_summarize:
        run_index(args)

    assert mock_summarize.call_args.kwargs["dry_run"] is True
    assert not (tmp_path / ".athena").exists()


def test_run_index_success_writes_root_summary_and_saves_manifest(tmp_path):
    (tmp_path / "a.py").write_text("print(1)", encoding="utf-8")
    args = make_args(path=str(tmp_path))

    with patch("athena.cli.command_exists", return_value=True), patch(
        "athena.cli.summarize_files_parallel", return_value={}
    ), patch(
        "athena.cli.summarize_dir", return_value="  root summary  "
    ):
        run_index(args)

    output_dir = tmp_path / ".athena"
    assert (output_dir / "summary.atn.md").read_text(encoding="utf-8") == "root summary\n"
    assert (output_dir / "manifest.json").exists()


def test_run_index_removes_orphaned_summaries(tmp_path):
    (tmp_path / "a.py").write_text("print(1)", encoding="utf-8")
    output_dir = tmp_path / ".athena"
    tree_dir = output_dir / "tree"
    tree_dir.mkdir(parents=True)
    orphan_summary = tree_dir / "removed.py.atn.md"
    orphan_summary.write_text("stale", encoding="utf-8")

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        '{"version": 1, "entries": {"removed.py": '
        '{"hash": "x", "summary_path": "removed.py.atn.md", "type": "file"}}}',
        encoding="utf-8",
    )

    args = make_args(path=str(tmp_path))

    with patch("athena.cli.command_exists", return_value=True), patch(
        "athena.cli.summarize_files_parallel", return_value={}
    ), patch(
        "athena.cli.summarize_dir", return_value="root summary"
    ):
        run_index(args)

    assert not orphan_summary.exists()


def test_run_index_forwards_force_flag(tmp_path):
    (tmp_path / "a.py").write_text("print(1)", encoding="utf-8")
    args = make_args(path=str(tmp_path), force=True)

    with patch("athena.cli.command_exists", return_value=True), patch(
        "athena.cli.summarize_files_parallel", return_value={}
    ), patch(
        "athena.cli.summarize_dir", return_value="root summary"
    ) as mock_summarize:
        run_index(args)

    assert mock_summarize.call_args.kwargs["force"] is True


def test_run_index_forwards_workers_and_model_to_summarize_files_parallel(tmp_path):
    (tmp_path / "a.py").write_text("print(1)", encoding="utf-8")
    args = make_args(path=str(tmp_path), workers=8, model="sonnet")

    with patch("athena.cli.command_exists", return_value=True), patch(
        "athena.cli.summarize_files_parallel", return_value={}
    ) as mock_parallel, patch(
        "athena.cli.summarize_dir", return_value="root summary"
    ) as mock_dir:
        run_index(args)

    assert mock_parallel.call_args.kwargs["max_workers"] == 8
    assert mock_parallel.call_args.kwargs["model"] == "sonnet"
    assert mock_dir.call_args.kwargs["model"] == "sonnet"


def test_run_index_empty_model_string_becomes_none(tmp_path):
    (tmp_path / "a.py").write_text("print(1)", encoding="utf-8")
    args = make_args(path=str(tmp_path), model="")

    with patch("athena.cli.command_exists", return_value=True), patch(
        "athena.cli.summarize_files_parallel", return_value={}
    ) as mock_parallel, patch(
        "athena.cli.summarize_dir", return_value="root summary"
    ) as mock_dir:
        run_index(args)

    assert mock_parallel.call_args.kwargs["model"] is None
    assert mock_dir.call_args.kwargs["model"] is None


def test_run_index_passes_file_summaries_from_parallel_pass_to_summarize_dir(
    tmp_path,
):
    (tmp_path / "a.py").write_text("print(1)", encoding="utf-8")
    args = make_args(path=str(tmp_path))
    sentinel = {"a.py": "precomputed"}

    with patch("athena.cli.command_exists", return_value=True), patch(
        "athena.cli.summarize_files_parallel", return_value=sentinel
    ), patch(
        "athena.cli.summarize_dir", return_value="root summary"
    ) as mock_dir:
        run_index(args)

    assert mock_dir.call_args.kwargs["file_summaries"] is sentinel


def test_run_index_prints_gitignore_tip_when_missing_entry(tmp_path, capsys):
    (tmp_path / "a.py").write_text("print(1)", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("node_modules\n", encoding="utf-8")
    args = make_args(path=str(tmp_path))

    with patch("athena.cli.command_exists", return_value=True), patch(
        "athena.cli.summarize_files_parallel", return_value={}
    ), patch(
        "athena.cli.summarize_dir", return_value="root summary"
    ):
        run_index(args)

    captured = capsys.readouterr()
    assert "[TIP]" in captured.out


def test_run_index_no_gitignore_tip_when_already_present(tmp_path, capsys):
    (tmp_path / "a.py").write_text("print(1)", encoding="utf-8")
    (tmp_path / ".gitignore").write_text(".athena/\n", encoding="utf-8")
    args = make_args(path=str(tmp_path))

    with patch("athena.cli.command_exists", return_value=True), patch(
        "athena.cli.summarize_dir", return_value="root summary"
    ):
        run_index(args)

    captured = capsys.readouterr()
    assert "[TIP]" not in captured.out


# ---------------------------------------------------------------------------
# run_show
# ---------------------------------------------------------------------------


def test_run_show_root_summary(tmp_path):
    output_dir = tmp_path / ".athena"
    output_dir.mkdir()
    (output_dir / "summary.atn.md").write_text("root content", encoding="utf-8")
    args = MagicMock(target=".", path=str(tmp_path))

    run_show(args)


def test_run_show_root_summary_prints_content(tmp_path, capsys):
    output_dir = tmp_path / ".athena"
    output_dir.mkdir()
    (output_dir / "summary.atn.md").write_text("root content", encoding="utf-8")
    args = MagicMock(target=".", path=str(tmp_path))

    run_show(args)

    captured = capsys.readouterr()
    assert "root content" in captured.out


def test_run_show_file_summary(tmp_path, capsys):
    tree_dir = tmp_path / ".athena" / "tree"
    tree_dir.mkdir(parents=True)
    (tree_dir / "src" / "a.py.atn.md").parent.mkdir(parents=True)
    (tree_dir / "src" / "a.py.atn.md").write_text("file summary", encoding="utf-8")
    args = MagicMock(target="src/a.py", path=str(tmp_path))

    run_show(args)

    captured = capsys.readouterr()
    assert "file summary" in captured.out


def test_run_show_dir_summary(tmp_path, capsys):
    tree_dir = tmp_path / ".athena" / "tree"
    sub_dir = tree_dir / "src"
    sub_dir.mkdir(parents=True)
    (sub_dir / "_dir_summary.atn.md").write_text("dir summary", encoding="utf-8")
    args = MagicMock(target="src", path=str(tmp_path))

    run_show(args)

    captured = capsys.readouterr()
    assert "dir summary" in captured.out


def test_run_show_missing_summary_exits(tmp_path):
    args = MagicMock(target="nope", path=str(tmp_path))

    with pytest.raises(SystemExit) as exc_info:
        run_show(args)

    assert exc_info.value.code == 1


def test_run_show_strips_leading_trailing_slashes(tmp_path, capsys):
    tree_dir = tmp_path / ".athena" / "tree"
    sub_dir = tree_dir / "src"
    sub_dir.mkdir(parents=True)
    (sub_dir / "_dir_summary.atn.md").write_text("dir summary", encoding="utf-8")
    args = MagicMock(target="/src/", path=str(tmp_path))

    run_show(args)

    captured = capsys.readouterr()
    assert "dir summary" in captured.out


# ---------------------------------------------------------------------------
# parse_args: remember / recall
# ---------------------------------------------------------------------------


def test_parse_argsRemember_defaults(monkeypatch):
    set_argv(monkeypatch, "remember", "decision", "docs/adr.md")

    args = parse_args()

    assert args.command == "remember"
    assert args.kind == "decision"
    assert args.arquivo == "docs/adr.md"
    assert args.path == "."
    assert args.backend == DEFAULT_BACKEND


def test_parse_args_remember_rejects_bad_kind(monkeypatch):
    set_argv(monkeypatch, "remember", "bogus", "x.md")

    with pytest.raises(SystemExit):
        parse_args()


def test_parse_args_recall_defaults(monkeypatch):
    set_argv(monkeypatch, "recall", "como funciona o cache")

    args = parse_args()

    assert args.command == "recall"
    assert args.consulta == "como funciona o cache"
    assert args.path == "."
    assert args.k == 5


# ---------------------------------------------------------------------------
# run_remember / run_recall (memória local, sem rede)
# ---------------------------------------------------------------------------


def _remember_args(tmp_path, kind="decision", arquivo="adr.md", backend="claude"):
    return MagicMock(
        path=str(tmp_path), kind=kind, arquivo=arquivo, backend=backend
    )


def test_run_remember_stores_file_text(tmp_path, capsys):
    (tmp_path / "adr.md").write_text(
        "Vamos usar sqlite para a memoria local.", encoding="utf-8"
    )
    args = _remember_args(tmp_path)

    with patch("athena.cli.resolve_backend", return_value="claude"):
        run_remember(args)

    captured = capsys.readouterr()
    assert "[OK]" in captured.out
    assert (tmp_path / ".thero" / "memory" / "index.sqlite3").exists()


def test_run_remember_dedupes_same_content(tmp_path):
    (tmp_path / "a.md").write_text("mesma coisa", encoding="utf-8")
    (tmp_path / "b.md").write_text("mesma coisa", encoding="utf-8")

    with patch("athena.cli.resolve_backend", return_value="claude"):
        run_remember(_remember_args(tmp_path, arquivo="a.md"))
        run_remember(_remember_args(tmp_path, arquivo="b.md"))

    from athena.memory import MemoryStore

    store = MemoryStore.for_project(tmp_path)
    try:
        assert store.count() == 1
    finally:
        store.close()


def test_run_remember_uses_embedding_when_local(tmp_path):
    (tmp_path / "adr.md").write_text("decisao com vetor", encoding="utf-8")
    args = _remember_args(tmp_path, backend="auto")

    with patch(
        "athena.cli.resolve_backend", return_value="local"
    ), patch("athena.cli.ollama_client.ollama_embed", return_value=[0.1, 0.2]) as mock_embed:
        run_remember(args)

    mock_embed.assert_called_once()


def test_run_remember_missing_file_exits(tmp_path):
    args = _remember_args(tmp_path, arquivo="nao_existe.md")

    with pytest.raises(SystemExit) as exc_info:
        run_remember(args)

    assert exc_info.value.code == 1


def test_run_remember_empty_file_exits(tmp_path):
    (tmp_path / "empty.md").write_text("   \n", encoding="utf-8")
    args = _remember_args(tmp_path, arquivo="empty.md")

    with pytest.raises(SystemExit) as exc_info:
        run_remember(args)

    assert exc_info.value.code == 1


def test_run_recall_empty_store_informs_user(tmp_path, capsys):
    args = MagicMock(path=str(tmp_path), consulta="nada", k=5, backend="claude")

    with patch("athena.cli.resolve_backend", return_value="claude"):
        run_recall(args)

    captured = capsys.readouterr()
    assert "vazia" in captured.out.lower()


def test_run_recall_finds_indexed_decision(tmp_path, capsys):
    (tmp_path / "adr.md").write_text(
        "cache incremental usa hash de arquivo", encoding="utf-8"
    )
    with patch("athena.cli.resolve_backend", return_value="claude"):
        run_remember(_remember_args(tmp_path))

    recall_args = MagicMock(
        path=str(tmp_path), consulta="cache incremental hash", k=5, backend="claude"
    )
    with patch("athena.cli.resolve_backend", return_value="claude"):
        run_recall(recall_args)

    captured = capsys.readouterr()
    assert "cache incremental" in captured.out
    assert "adr.md" in captured.out


def test_main_dispatches_remember_and_recall(monkeypatch, tmp_path):
    (tmp_path / "adr.md").write_text("x", encoding="utf-8")

    set_argv(monkeypatch, "remember", "note", str(tmp_path / "adr.md"), str(tmp_path))
    with patch("athena.cli.run_remember") as mock_rem, patch(
        "athena.cli.resolve_backend", return_value="claude"
    ):
        main()
    mock_rem.assert_called_once()

    set_argv(monkeypatch, "recall", "abc", str(tmp_path))
    with patch("athena.cli.run_recall") as mock_rec:
        main()
    mock_rec.assert_called_once()
