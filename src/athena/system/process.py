from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


FILE_ATTRIBUTE_HIDDEN = 0x2


def hide_windows_path(path: Path) -> bool:
    """
    Marca `path` com o atributo Hidden do NTFS, no Windows. No-op (retorna
    False) em outros SOs. Um prefixo "." ja basta para ocultar em
    Linux/macOS, mas o Windows Explorer/"dir" ignoram esse prefixo — so
    o atributo Hidden real oculta a pasta la.
    """

    if os.name != "nt":
        return False

    import ctypes

    result = ctypes.windll.kernel32.SetFileAttributesW(  # type: ignore[attr-defined]
        str(path),
        FILE_ATTRIBUTE_HIDDEN,
    )

    return bool(result)


def run_command(
command: list[str],
*,
cwd: Path | None = None,
capture: bool = True,
text: bool = True,
input_text: str | None = None,
) -> subprocess.CompletedProcess:
    """
    Execute a command reliably on Windows and Unix-like systems.

    Windows installs the Claude Code launcher as a .cmd file.
    Explicitly use the Windows launcher when necessary.
    """
    if not command:
        raise ValueError("Command cannot be empty.")

    executable = command[0]

    if os.name == "nt":
        # No Windows, "claude" pode ser instalado como claude.cmd
        # (shim do npm) ou claude.exe, dependendo do metodo de
        # instalacao. shutil.which resolve o shim/launcher correto
        # via PATH + PATHEXT; sem isso, subprocess com shell=False
        # falha com FileNotFoundError mesmo com o comando no PATH.
        resolved = shutil.which(executable)

        if resolved is not None:
            executable = resolved

        command = [executable, *command[1:]]

    # Sem "encoding" explícito, o Windows decodifica stdout/stderr
    # usando a codepage do console (ex.: cp1252), corrompendo
    # acentos que o Claude retorna em UTF-8.
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        capture_output=capture,
        text=text,
        encoding="utf-8" if text else None,
        input=input_text,
        shell=False,
    )
