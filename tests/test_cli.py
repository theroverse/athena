from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from athena.cli import main, parse_args, run_index, run_show
from athena.settings import DEFAULT_MAX_FILES
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


def test_parse_args_index_with_flags(monkeypatch):
    set_argv(monkeypatch, "index", "/some/project", "--force", "--dry-run", "--max-files", "999")

    args = parse_args()

    assert args.path == "/some/project"
    assert args.force is True
    assert args.dry_run is True
    assert args.max_files == 999


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
    defaults = dict(path=".", force=False, dry_run=False, max_files=DEFAULT_MAX_FILES)
    defaults.update(overrides)
    return MagicMock(**defaults)


def test_run_index_exits_when_claude_missing_and_not_dry_run(tmp_path):
    args = make_args(path=str(tmp_path))

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


def test_run_index_zero_files_returns_without_creating_manifest(tmp_path):
    args = make_args(path=str(tmp_path))

    with patch("athena.cli.command_exists", return_value=True):
        run_index(args)

    assert not (tmp_path / ".athena" / "manifest.json").exists()


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
        "athena.cli.summarize_dir", return_value="root summary"
    ):
        run_index(args)

    assert not orphan_summary.exists()


def test_run_index_forwards_force_flag(tmp_path):
    (tmp_path / "a.py").write_text("print(1)", encoding="utf-8")
    args = make_args(path=str(tmp_path), force=True)

    with patch("athena.cli.command_exists", return_value=True), patch(
        "athena.cli.summarize_dir", return_value="root summary"
    ) as mock_summarize:
        run_index(args)

    assert mock_summarize.call_args.kwargs["force"] is True


def test_run_index_prints_gitignore_tip_when_missing_entry(tmp_path, capsys):
    (tmp_path / "a.py").write_text("print(1)", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("node_modules\n", encoding="utf-8")
    args = make_args(path=str(tmp_path))

    with patch("athena.cli.command_exists", return_value=True), patch(
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
