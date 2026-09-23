from __future__ import annotations

from unittest.mock import patch, MagicMock

from athena.summarizer.claude_client import call_claude


def test_call_claude_returns_none_when_claude_missing():
    with patch(
        "athena.summarizer.claude_client.command_exists", return_value=False
    ), patch("athena.summarizer.claude_client.run_command") as mock_run:
        result = call_claude("prompt")

    assert result is None
    mock_run.assert_not_called()


def test_call_claude_returns_none_on_nonzero_returncode():
    fake_result = MagicMock(returncode=1, stdout="", stderr="boom")
    with patch(
        "athena.summarizer.claude_client.command_exists", return_value=True
    ), patch(
        "athena.summarizer.claude_client.run_command", return_value=fake_result
    ):
        result = call_claude("prompt")

    assert result is None


def test_call_claude_returns_none_on_empty_stdout():
    fake_result = MagicMock(returncode=0, stdout="   ", stderr="")
    with patch(
        "athena.summarizer.claude_client.command_exists", return_value=True
    ), patch(
        "athena.summarizer.claude_client.run_command", return_value=fake_result
    ):
        result = call_claude("prompt")

    assert result is None


def test_call_claude_returns_stripped_stdout_on_success():
    fake_result = MagicMock(returncode=0, stdout="  hello world  \n", stderr="")
    with patch(
        "athena.summarizer.claude_client.command_exists", return_value=True
    ), patch(
        "athena.summarizer.claude_client.run_command", return_value=fake_result
    ) as mock_run:
        result = call_claude("my prompt", cwd="/proj")

    assert result == "hello world"
    mock_run.assert_called_once_with(
        ["claude", "-p"], capture=True, cwd="/proj", input_text="my prompt"
    )


def test_call_claude_omits_model_flag_by_default():
    fake_result = MagicMock(returncode=0, stdout="hi", stderr="")
    with patch(
        "athena.summarizer.claude_client.command_exists", return_value=True
    ), patch(
        "athena.summarizer.claude_client.run_command", return_value=fake_result
    ) as mock_run:
        call_claude("my prompt")

    called_command = mock_run.call_args.args[0]
    assert called_command == ["claude", "-p"]


def test_call_claude_forwards_model_flag():
    fake_result = MagicMock(returncode=0, stdout="hi", stderr="")
    with patch(
        "athena.summarizer.claude_client.command_exists", return_value=True
    ), patch(
        "athena.summarizer.claude_client.run_command", return_value=fake_result
    ) as mock_run:
        call_claude("my prompt", model="haiku")

    called_command = mock_run.call_args.args[0]
    assert called_command == ["claude", "-p", "--model", "haiku"]
