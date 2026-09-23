"""Memória local leve da Athena (banco vetorial / cache de contexto).

Camada stdlib-only: persistência em ``sqlite3`` com busca por similaridade
de cosseno sobre embeddings do Ollama quando disponível, e fallback
TF-IDF puro (sem nenhuma dependência) quando offline.
"""

from athena.memory.store import MemoryItem, MemoryStore

__all__ = ["MemoryItem", "MemoryStore"]
