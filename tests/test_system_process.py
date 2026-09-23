from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from athena.system.process import command_exists, hide_windows_path, run_command


def test_command_exists_true_when_which_finds_it():
    with patch("athena.system.process.shutil.which", return_value="/usr/bin/git"):
        assert command_exists("git") is True


def test_command_exists_false_when_which_returns_none():
    with patch("athena.system.process.shutil.which", return_value=None):
        assert command_exists("nope") is False


def test_run_command_raises_on_empty_command():
    with pytest.raises(ValueError):
        run_command([])


@patch("athena.system.process.shutil.which", return_value=r"C:\tools\claude.cmd")
@patch("athena.system.process.os.name", "nt")
@patch("athena.system.process.subprocess.run")
def test_run_command_maps_claude_launcher_on_windows(mock_run, _mock_which):
    run_command(["claude", "-p"])

    called_command = mock_run.call_args.args[0]
    assert called_command[0] == r"C:\tools\claude.cmd"
    assert called_command[1:] == ["-p"]


@patch("athena.system.process.shutil.which", return_value=None)
@patch("athena.system.process.os.name", "nt")
@patch("athena.system.process.subprocess.run")
def test_run_command_leaves_unknown_executable_unmapped_on_windows(mock_run, _mock_which):
    run_command(["python", "-V"])

    called_command = mock_run.call_args.args[0]
    assert called_command[0] == "python"


@patch("athena.system.process.os.name", "posix")
@patch("athena.system.process.subprocess.run")
def test_run_command_does_not_map_launchers_on_posix(mock_run):
    run_command(["claude", "-p"])

    called_command = mock_run.call_args.args[0]
    assert called_command[0] == "claude"


@patch("athena.system.process.subprocess.run")
def test_run_command_passes_utf8_encoding_when_text(mock_run):
    run_command(["echo", "hi"], text=True)

    assert mock_run.call_args.kwargs["encoding"] == "utf-8"


@patch("athena.system.process.subprocess.run")
def test_run_command_no_encoding_when_not_text(mock_run):
    run_command(["echo", "hi"], text=False)

    assert mock_run.call_args.kwargs["encoding"] is None


@patch("athena.system.process.subprocess.run")
def test_run_command_forwards_cwd_capture_input(mock_run):
    run_command(["cmd"], cwd="/some/dir", capture=False, input_text="hello")

    kwargs = mock_run.call_args.kwargs
    assert kwargs["cwd"] == "/some/dir"
    assert kwargs["capture_output"] is False
    assert kwargs["input"] == "hello"
    assert kwargs["shell"] is False


@patch("athena.system.process.subprocess.run")
def test_run_command_cwd_none_when_not_given(mock_run):
    run_command(["cmd"])

    assert mock_run.call_args.kwargs["cwd"] is None


@patch("athena.system.process.os.name", "posix")
def test_hide_windows_path_is_noop_on_posix():
    assert hide_windows_path(Path("/some/dir")) is False


@patch("athena.system.process.os.name", "nt")
@patch("ctypes.windll.kernel32.SetFileAttributesW", create=True)
def test_hide_windows_path_sets_hidden_attribute_on_windows(mock_set_attrs):
    mock_set_attrs.return_value = 1

    assert hide_windows_path(Path("C:/some/.athena")) is True

    mock_set_attrs.assert_called_once_with("C:\\some\\.athena", 0x2)


@patch("athena.system.process.os.name", "nt")
@patch("ctypes.windll.kernel32.SetFileAttributesW", create=True)
def test_hide_windows_path_returns_false_when_winapi_call_fails(mock_set_attrs):
    mock_set_attrs.return_value = 0

    assert hide_windows_path(Path("C:/some/.athena")) is False
