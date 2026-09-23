from __future__ import annotations

from pathlib import Path

from athena.system.process import command_exists, run_command


def call_claude(
    prompt: str,
    *,
    cwd: Path | None = None,
    model: str | None = None,
) -> str | None:

    if not command_exists("claude"):
        print(
            "[ERROR] Claude Code executable was not found."
        )
        return None

    command = ["claude", "-p"]

    if model is not None:
        command += ["--model", model]

    result = run_command(
        command,
        capture=True,
        cwd=cwd,
        input_text=prompt,
    )

    if result.returncode != 0:

        print(
            "[ERROR] Claude returned an error."
        )

        if result.stderr:
            print(result.stderr)

        return None

    output = result.stdout.strip()

    if not output:
        print(
            "[ERROR] Claude returned empty output."
        )
        return None

    return output
