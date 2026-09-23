from __future__ import annotations

import pytest

from athena.ignore import IgnoreMatcher, build_matcher


def make_matcher(*lines: str) -> IgnoreMatcher:
    matcher = IgnoreMatcher()
    for line in lines:
        matcher.add_line(line)
    return matcher


# (gitignore_lines, path, is_dir, expected_ignored)
CASES = [
    # Blank lines and comments are no-ops.
    (["", "  ", "# comment"], "foo.py", False, False),
    # Plain name matches at any depth (no leading "/").
    (["node_modules"], "node_modules", True, True),
    (["node_modules"], "src/node_modules", True, True),
    # Known limitation: matcher checks each path independently, it does
    # not recurse from an ignored ancestor directory like real git does.
    (["node_modules"], "src/node_modules/file.js", False, False),
    # Leading "/" anchors to the root only.
    (["/build"], "build", True, True),
    (["/build"], "src/build", True, False),
    # Trailing "/" matches directories only.
    (["logs/"], "logs", True, True),
    (["logs/"], "logs", False, False),
    # "*" does not cross "/".
    (["*.log"], "app.log", False, True),
    (["*.log"], "sub/app.log", False, True),
    (["a*b"], "aXXb", False, True),
    (["a*b"], "a/b", False, False),
    # "?" matches exactly one non-"/" character.
    (["file?.txt"], "file1.txt", False, True),
    (["file?.txt"], "file12.txt", False, False),
    # Character classes.
    (["file[12].txt"], "file1.txt", False, True),
    (["file[12].txt"], "file3.txt", False, False),
    (["file[!12].txt"], "file3.txt", False, True),
    (["file[!12].txt"], "file1.txt", False, False),
    # "**" matches one or more segments (known limitation: unlike real
    # gitignore, it does NOT also match zero segments).
    (["a/**/b"], "a/b", False, False),
    (["a/**/b"], "a/x/b", False, True),
    (["a/**/b"], "a/x/y/b", False, True),
    (["a/**/b"], "a/x/y/c", False, False),
    # Negation re-includes a previously ignored path.
    (["*.log", "!keep.log"], "keep.log", False, False),
    (["*.log", "!keep.log"], "drop.log", False, True),
    # Later rules win over earlier ones (gitignore semantics).
    (["*.log", "!keep.log", "*.log"], "keep.log", False, True),
    # Path with no "/" anywhere still matches nested occurrences.
    (["*.pyc"], "a/b/c.pyc", False, True),
]


@pytest.mark.parametrize("lines,path,is_dir,expected", CASES)
def test_gitignore_style_cases(lines, path, is_dir, expected):
    matcher = make_matcher(*lines)
    assert matcher.is_ignored(path, is_dir) is expected


def test_unterminated_bracket_is_treated_as_literal():
    # "[" with no closing "]" is not a valid character class; matcher
    # falls back to treating "[" as a literal character.
    matcher = make_matcher("file[abc.txt")

    assert matcher.is_ignored("file[abc.txt", False) is True
    assert matcher.is_ignored("filea.txt", False) is False


def test_bracket_class_with_leading_close_bracket_literal():
    # "[]" as the first character inside a class is a literal "]",
    # per gitignore convention (mirrors POSIX bracket expressions).
    matcher = make_matcher("file[]a].txt")

    assert matcher.is_ignored("file].txt", False) is True
    assert matcher.is_ignored("filea.txt", False) is True


def test_lone_negation_marker_is_a_noop():
    matcher = make_matcher("!")

    assert matcher.is_ignored("anything", False) is False


def test_always_ignored_names_even_without_rules():
    matcher = IgnoreMatcher()

    assert matcher.is_ignored(".git", True) is True
    assert matcher.is_ignored("sub/.git", True) is True
    assert matcher.is_ignored(".athena", True) is True


def test_always_ignored_cannot_be_negated_by_user_rule():
    # ALWAYS_IGNORED_NAMES check happens before rule evaluation and short
    # circuits, so a "!" rule cannot bring .git back.
    matcher = make_matcher("!.git")

    assert matcher.is_ignored(".git", True) is True


def test_match_rules_returns_none_when_nothing_matches():
    matcher = make_matcher("*.log")

    assert matcher.match_rules("app.py", False) is None


def test_match_rules_returns_bool_when_a_rule_matches():
    matcher = make_matcher("*.log", "!keep.log")

    assert matcher.match_rules("app.log", False) is True
    assert matcher.match_rules("keep.log", False) is False


def test_build_matcher_reads_gitignore_from_project_root(tmp_path):
    (tmp_path / ".gitignore").write_text("*.log\n", encoding="utf-8")

    matcher = build_matcher(tmp_path)

    assert matcher.is_ignored("app.log", False) is True
    assert matcher.is_ignored("app.py", False) is False


def test_build_matcher_without_gitignore_file(tmp_path):
    matcher = build_matcher(tmp_path)

    assert matcher.is_ignored("app.py", False) is False


def test_build_matcher_merges_extra_ignore_file(tmp_path):
    (tmp_path / ".gitignore").write_text("*.log\n", encoding="utf-8")
    extra = tmp_path / ".athenaignore"
    extra.write_text("*.tmp\n", encoding="utf-8")

    matcher = build_matcher(tmp_path, extra_ignore_file=extra)

    assert matcher.is_ignored("app.log", False) is True
    assert matcher.is_ignored("scratch.tmp", False) is True
    assert matcher.is_ignored("app.py", False) is False


def test_load_file_handles_crlf_line_endings(tmp_path):
    gitignore = tmp_path / ".gitignore"
    gitignore.write_bytes(b"*.log\r\n!keep.log\r\n")

    matcher = build_matcher(tmp_path)

    assert matcher.is_ignored("drop.log", False) is True
    assert matcher.is_ignored("keep.log", False) is False
