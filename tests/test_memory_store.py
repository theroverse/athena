from __future__ import annotations

import pytest

from athena.memory import MemoryItem, MemoryStore
from athena.memory.store import VALID_KINDS, _cosine, _tokenize


@pytest.fixture
def store(tmp_path):
    instance = MemoryStore(tmp_path / "memory" / "index.sqlite3")
    yield instance
    instance.close()


# -- escrita / dedupe -------------------------------------------------------


def test_add_returns_incrementing_ids(store):
    first = store.add("note", "primeira decisao arquitetural")
    second = store.add("convention", "usar snake_case em funcoes")

    assert first != second
    assert store.count() == 2


def test_add_is_deterministic_and_dedupes_by_hash(store):
    a = store.add("decision", "usar sqlite para a memoria")
    b = store.add("decision", "usar sqlite para a memoria")

    assert a == b
    assert store.count() == 1


def test_add_updates_embedding_only_when_provided(store):
    item_id = store.add("note", "texto com embedding posterior")
    # Re-registrar sem embedding não deve apagar o existente (COALESCE).
    store.add("note", "texto com embedding posterior", embedding=[0.1, 0.2, 0.3])
    store.add("note", "texto com embedding posterior")

    item = next(i for i in store.all() if i.id == item_id)
    assert item.embedding == [0.1, 0.2, 0.3]


def test_add_rejects_invalid_kind(store):
    with pytest.raises(ValueError):
        store.add("bogus", "kind inexistente")


def test_upsert_is_alias_of_add(store):
    kind = sorted(VALID_KINDS)[0]
    assert store.upsert(kind, "mesmo conteudo") == store.upsert(kind, "mesmo conteudo")


def test_for_project_uses_thero_memory_layout(tmp_path):
    project = tmp_path / "proj"
    instance = MemoryStore.for_project(project)
    try:
        assert instance.db_path == project / ".thero" / "memory" / "index.sqlite3"
        assert instance.db_path.parent.exists()
    finally:
        instance.close()


# -- leitura ----------------------------------------------------------------


def test_all_returns_items_newest_first(store):
    store.add("note", "antigo")
    store.add("note", "novo")
    items = store.all()

    assert [i.text for i in items] == ["novo", "antigo"]
    assert all(isinstance(i, MemoryItem) for i in items)


def test_source_path_is_persisted(store):
    store.add("convention", "regra", source_path="src/athena/cli.py")
    item = store.all()[0]

    assert item.source_path == "src/athena/cli.py"


# -- busca: TF-IDF (fallback offline) ---------------------------------------


def test_search_on_empty_store_returns_nothing(store):
    assert store.search("qualquer coisa") == []


def test_tfidf_search_ranks_by_relevance(store):
    store.add("convention", "python usa snake_case para nomes de funcao")
    store.add("decision", "banco de memoria usa sqlite local")
    store.add("note", "a interface grafica usa webview")

    results = store.search("sqlite memoria banco", embed_fn=None)

    assert results
    top_item, top_score = results[0]
    assert top_item.text == "banco de memoria usa sqlite local"
    assert top_score > 0


def test_tfidf_respects_top_k(store):
    for i in range(5):
        store.add("note", f"nota numero {i} sobre o tema buscavel buscavel")

    results = store.search("buscavel tema", k=2, embed_fn=None)

    assert len(results) == 2


# -- busca: cosseno (embeddings) + lazy persist ------------------------------


def _fake_embed(text: str) -> "list[float] | None":
    # Embedding determinístico: dimensão fixa derivada do comprimento.
    return [float(len(text) % 7), float(len(text)), 1.0]


def test_cosine_search_persists_embeddings_lazily(store):
    store.add("note", "alpha")
    store.add("note", "beta")

    results = store.search("alpha", embed_fn=_fake_embed)

    assert results
    # Itens antes sem embedding agora ficaram vetorizados no banco.
    reloaded = MemoryStore(store.db_path)
    try:
        assert all(i.embedding is not None for i in reloaded.all())
    finally:
        reloaded.close()


def test_cosine_used_when_embeddings_consistent(store):
    store.add("note", "greeting hello world", embedding=[1.0, 0.0, 0.0])
    store.add("note", "unrelated topic", embedding=[0.0, 1.0, 0.0])

    def embed_fn(_text: str):
        return [1.0, 0.0, 0.0]

    results = store.search("hello there", embed_fn=embed_fn)

    assert results[0][0].text == "greeting hello world"


def test_dimension_mismatch_falls_back_to_tfidf(store):
    # Item com embedding de 2 dimensões; query com 3 → incompatível.
    store.add("note", "sqlite memoria banco", embedding=[1.0, 0.0])
    store.add("note", "完全 diferente unrelated", embedding=[0.0, 1.0])

    def embed_fn(_text: str):
        return [1.0, 0.0, 0.0]

    results = store.search("sqlite memoria banco", embed_fn=embed_fn)

    # Ainda retorna algo (fallback TF-IDF), e o melhor match é o item certo.
    assert results
    assert results[0][0].text == "sqlite memoria banco"


def test_cosine_falls_back_when_embed_fn_returns_none(store):
    store.add("note", "sqlite memoria banco")
    store.add("note", "outra coisa sem relacao")

    results = store.search("sqlite", embed_fn=lambda _t: None)

    assert results
    assert results[0][0].text == "sqlite memoria banco"


# -- helpers puros -----------------------------------------------------------


def test_tokenize_lowercases_and_splits_words():
    assert _tokenize("Snake_Case Função") == ["snake_case", "função"]


def test_cosine_orthogonal_vectors_score_zero():
    assert _cosine([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_identical_vectors_score_one():
    assert _cosine([2.0, 1.0], [4.0, 2.0]) == pytest.approx(1.0)


def test_cosine_zero_vector_is_safe():
    assert _cosine([0.0, 0.0], [1.0, 1.0]) == 0.0
