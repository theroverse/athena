from __future__ import annotations

import re
from pathlib import Path

from athena.settings import ALWAYS_IGNORED_NAMES


def _segment_to_regex(segment: str) -> str:
    """
    Traduz um segmento de caminho (sem "/") com glob estilo gitignore
    para uma sub-regex. "*" e "?" nunca cruzam "/".
    """

    parts: list[str] = []
    i = 0
    length = len(segment)

    while i < length:
        char = segment[i]

        if char == "*":
            parts.append("[^/]*")
        elif char == "?":
            parts.append("[^/]")
        elif char == "[":
            end = i + 1
            if end < length and segment[end] == "!":
                end += 1
            if end < length and segment[end] == "]":
                end += 1
            while end < length and segment[end] != "]":
                end += 1

            if end >= length:
                parts.append(re.escape(char))
                i += 1
                continue

            raw_class = segment[i:end + 1]
            if raw_class.startswith("[!"):
                raw_class = "[^" + raw_class[2:]
            parts.append(raw_class)
            i = end
        else:
            parts.append(re.escape(char))

        i += 1

    return "".join(parts)


def _pattern_to_regex(pattern: str) -> tuple[re.Pattern[str], bool]:

    dir_only = pattern.endswith("/")
    if dir_only:
        pattern = pattern[:-1]

    leading_slash = pattern.startswith("/")
    if leading_slash:
        pattern = pattern[1:]

    # Padrão sem "/" no meio (e sem "/" no início) pode casar em
    # qualquer profundidade, como o gitignore real.
    anchored = leading_slash or ("/" in pattern)

    segments = pattern.split("/")
    regex_segments = [
        ".*" if segment == "**" else _segment_to_regex(segment)
        for segment in segments
    ]
    body = "/".join(regex_segments)

    prefix = "^" if anchored else "^(?:.*/)?"

    return re.compile(prefix + body + "$"), dir_only


class IgnoreMatcher:
    """
    Matcher pragmático de padrões estilo .gitignore.

    Suporta: comentários, linhas em branco, negação ("!"), "/" no
    início (ancora na raiz), "/" no final (só diretório) e "**".

    Limitação conhecida: só lê o .gitignore/.athenaignore da raiz do
    projeto — não considera .gitignore aninhados em subpastas.
    """

    def __init__(self) -> None:
        self._rules: list[tuple[re.Pattern[str], bool, bool]] = []

    def add_line(self, line: str) -> None:

        line = line.rstrip("\n").rstrip("\r")
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            return

        negate = stripped.startswith("!")
        if negate:
            stripped = stripped[1:]

        if not stripped:
            return

        regex, dir_only = _pattern_to_regex(stripped)
        self._rules.append((regex, dir_only, negate))

    def load_file(self, path: Path) -> None:

        if not path.is_file():
            return

        text = path.read_text(encoding="utf-8", errors="replace")

        for raw_line in text.splitlines():
            self.add_line(raw_line)

    def match_rules(
        self,
        relative_posix_path: str,
        is_dir: bool,
    ) -> bool | None:
        """
        Igual a `is_ignored`, mas sem o atalho de ALWAYS_IGNORED_NAMES e
        distinguindo "nenhuma regra bateu" (None) de "regra bateu e
        desmarcou" (False). Usado para combinar varios .gitignore
        aninhados, onde regras de niveis mais profundos so devem
        sobrepor as de niveis acima quando realmente baterem.
        """

        result: bool | None = None

        for regex, dir_only, negate in self._rules:

            if dir_only and not is_dir:
                continue

            if regex.match(relative_posix_path):
                result = not negate

        return result

    def is_ignored(
        self,
        relative_posix_path: str,
        is_dir: bool,
    ) -> bool:

        name = relative_posix_path.rsplit("/", 1)[-1]

        if name in ALWAYS_IGNORED_NAMES:
            return True

        return bool(self.match_rules(relative_posix_path, is_dir))


def build_matcher(
    project_root: Path,
    extra_ignore_file: Path | None = None,
) -> IgnoreMatcher:

    matcher = IgnoreMatcher()

    matcher.load_file(project_root / ".gitignore")

    if extra_ignore_file is not None:
        matcher.load_file(extra_ignore_file)

    return matcher
