from __future__ import annotations

"""
Banco de memória local da Athena.

Guarda convenções de código, histórico e decisões arquiteturais num
SQLite (stdlib) em ``<projeto>/.thero/memory/index.sqlite3``, para
rechamar contexto sem recomprimir tudo do zero.

Busca por similaridade em dois modos, sem nenhuma dependência externa:

- **cosseno** sobre embeddings do Ollama (quando um ``embed_fn`` é
  fornecido e responde), e
- **TF-IDF** puro (``math``/``collections``) como fallback offline.

Nada aqui toca a rede por si só: ``embed_fn`` é injetado pelo chamador
(ex.: ``ollama_client.ollama_embed``). Os testes rodam com ``embed_fn``
fake ou ausente, jamais com rede real.
"""

import json
import math
import re
import sqlite3
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from athena.hashing import hash_text
from athena.settings import (
    MEMORY_DB_FILENAME,
    MEMORY_DEFAULT_TOP_K,
    MEMORY_DIRNAME,
    MEMORY_SUBDIR,
)

VALID_KINDS = {"convention", "history", "decision", "note"}

EmbedFn = Callable[[str], "list[float] | None"]

# Tokens de \w+ unicode, em minúsculas, para o TF-IDF de fallback.
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot / (norm_a * norm_b)


@dataclass
class MemoryItem:
    id: int
    kind: str
    source_path: str | None
    content_hash: str
    text: str
    updated_at: float
    embedding: list[float] | None = None


class MemoryStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    @classmethod
    def for_project(cls, project_root: Path) -> "MemoryStore":
        """Abre a memória padrão do projeto: ``<raiz>/.thero/memory/...``."""

        return cls(
            project_root / MEMORY_DIRNAME / MEMORY_SUBDIR / MEMORY_DB_FILENAME
        )

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                kind         TEXT NOT NULL,
                source_path  TEXT,
                content_hash TEXT UNIQUE NOT NULL,
                text         TEXT NOT NULL,
                embedding    TEXT,
                updated_at   REAL NOT NULL
            )
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "MemoryStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- escrita ------------------------------------------------------------

    def add(
        self,
        kind: str,
        text: str,
        source_path: str | None = None,
        embedding: list[float] | None = None,
    ) -> int:
        """
        Insere (ou atualiza, por dedupe de ``content_hash``) um item.
        Reuso da chave natural do conteúdo: registrar a mesma decisão de
        novo não duplica — atualiza o timestamp/embedding em vez disso.
        """

        if kind not in VALID_KINDS:
            raise ValueError(
                f"kind inválido {kind!r}; esperado um de {sorted(VALID_KINDS)}"
            )

        content_hash = hash_text(text)
        now = time.time()
        embedding_json = json.dumps(embedding) if embedding is not None else None
        source = str(source_path) if source_path is not None else None

        existing = self._conn.execute(
            "SELECT id FROM memory WHERE content_hash = ?", (content_hash,)
        ).fetchone()

        if existing is not None:
            self._conn.execute(
                """
                UPDATE memory
                   SET kind = ?, source_path = ?, text = ?,
                       embedding = COALESCE(?, embedding), updated_at = ?
                 WHERE id = ?
                """,
                (
                    kind,
                    source,
                    text,
                    embedding_json,
                    now,
                    existing["id"],
                ),
            )
            self._conn.commit()
            return int(existing["id"])

        cursor = self._conn.execute(
            """
            INSERT INTO memory
                (kind, source_path, content_hash, text, embedding, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (kind, source, content_hash, text, embedding_json, now),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def upsert(
        self,
        kind: str,
        text: str,
        source_path: str | None = None,
        embedding: list[float] | None = None,
    ) -> int:
        """Sinônimo explícito de ``add`` (o dedupe por hash já é um upsert)."""

        return self.add(kind, text, source_path=source_path, embedding=embedding)

    def _persist_embedding(self, item_id: int, embedding: list[float]) -> None:
        self._conn.execute(
            "UPDATE memory SET embedding = ? WHERE id = ?",
            (json.dumps(embedding), item_id),
        )
        self._conn.commit()

    # -- leitura ------------------------------------------------------------

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS n FROM memory").fetchone()
        return int(row["n"])

    def all(self) -> list[MemoryItem]:
        rows = self._conn.execute(
            "SELECT * FROM memory ORDER BY updated_at DESC"
        ).fetchall()
        return [self._row_to_item(row) for row in rows]

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> MemoryItem:
        raw_embedding = row["embedding"]
        embedding = json.loads(raw_embedding) if raw_embedding else None

        return MemoryItem(
            id=int(row["id"]),
            kind=row["kind"],
            source_path=row["source_path"],
            content_hash=row["content_hash"],
            text=row["text"],
            updated_at=float(row["updated_at"]),
            embedding=embedding,
        )

    # -- busca --------------------------------------------------------------

    def search(
        self,
        query: str,
        k: int = MEMORY_DEFAULT_TOP_K,
        embed_fn: EmbedFn | None = None,
    ) -> list[tuple[MemoryItem, float]]:
        """
        Retorna até ``k`` itens ordenados por relevância decrescente.

        Com um ``embed_fn`` funcional (e dimensões consistentes), usa
        cosseno vetorial; sem ele (Ollama fora do ar) ou com embeddings
        incompatíveis, cai para TF-IDF sobre o texto — sempre determinístico.
        """

        items = self.all()

        if not items:
            return []

        if embed_fn is not None:
            cosine = self._search_cosine(items, query, embed_fn)

            if cosine is not None:
                return cosine[:k]

        return self._search_tfidf(items, query)[:k]

    def _search_cosine(
        self,
        items: list[MemoryItem],
        query: str,
        embed_fn: EmbedFn,
    ) -> "list[tuple[MemoryItem, float]] | None":
        """
        Tenta busca vetorial. Devolve ``None`` para forçar o fallback
        TF-IDF se o query não vetorizar ou se houver incompatibilidade de
        dimensões entre embeddings (ex.: itens de um modelo antigo).
        """

        query_vec = embed_fn(query)

        if not query_vec:
            return None

        scored: list[tuple[MemoryItem, float]] = []

        for item in items:
            vec = item.embedding

            if vec is None:
                vec = embed_fn(item.text)

                if not vec:
                    return None

                self._persist_embedding(item.id, vec)
                item.embedding = vec

            if len(vec) != len(query_vec):
                return None

            scored.append((item, _cosine(query_vec, vec)))

        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored

    def _search_tfidf(
        self,
        items: list[MemoryItem],
        query: str,
    ) -> list[tuple[MemoryItem, float]]:
        """
        TF-IDF + cosseno em puro Python. idf suavizado ``log(1 + n/df)``
        para nunca dividir por zero nem zerar termos vistos em todos os
        documentos.
        """

        documents = [_tokenize(item.text) for item in items]
        n = len(documents)

        doc_freq: Counter = Counter()

        for tokens in documents:
            for term in set(tokens):
                doc_freq[term] += 1

        def idf(term: str) -> float:
            return math.log(1 + n / (1 + doc_freq.get(term, 0)))

        def weight_vector(tokens: list[str]) -> dict[str, float]:
            freq = Counter(tokens)
            total = sum(freq.values()) or 1
            return {
                term: (count / total) * idf(term)
                for term, count in freq.items()
            }

        query_vec = weight_vector(_tokenize(query))
        query_norm = math.sqrt(sum(value * value for value in query_vec.values()))

        scored: list[tuple[MemoryItem, float]] = []

        for item, tokens in zip(items, documents):
            doc_vec = weight_vector(tokens)
            doc_norm = math.sqrt(sum(value * value for value in doc_vec.values()))

            if query_norm == 0.0 or doc_norm == 0.0:
                score = 0.0
            else:
                dot = sum(
                    weight * doc_vec.get(term, 0.0)
                    for term, weight in query_vec.items()
                )
                score = dot / (query_norm * doc_norm)

            scored.append((item, score))

        # Estabilidade: desempata por id crescente quando os scores empatam.
        scored.sort(key=lambda pair: (-pair[1], pair[0].id))
        return scored
