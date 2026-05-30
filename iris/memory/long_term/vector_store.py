from __future__ import annotations

import threading
from typing import cast

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from loguru import logger
from rank_bm25 import BM25Okapi


class _ONNXEmbeddings(Embeddings):
    """LangChain Embeddings wrapper for chromadb's ONNX MiniLM embedding function."""

    def __init__(self) -> None:
        from chromadb.utils import embedding_functions as ef

        self._ef = cast(ef.EmbeddingFunction, ef.ONNXMiniLM_L6_V2())

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._ef(texts)  # type: ignore[return-value]

    def embed_query(self, text: str) -> list[float]:
        return self._ef([text])[0]  # type: ignore[return-value]


class VectorStore:
    """ChromaDB + BM25 ハイブリッド検索エンジン (LangChain統合)"""

    def __init__(self, path: str = ".iris/data/chroma_db"):
        self._embedding = _ONNXEmbeddings()
        self._lock = threading.Lock()
        self._db = Chroma(
            collection_name="semantic",
            embedding_function=self._embedding,
            persist_directory=path,
            collection_metadata={"hnsw:space": "cosine"},
        )
        self._bm25: BM25Okapi | None = None
        self._bm25_ids: list[str] = []

    # ---- CRUD ----

    def add(self, entry: dict, account_id: str = "") -> None:
        with self._lock:
            eid = entry.get("id", str(hash(entry.get("content", ""))))
            content = entry.get("content", "")
            metadata = {
                "id": eid,
                "type": entry.get("type", "lesson"),
                "tags": ",".join(entry.get("tags", [])),
                "timestamp": entry.get("timestamp", ""),
                "account_id": account_id,
            }
            self._db.add_texts(texts=[content], metadatas=[metadata], ids=[eid])
            self._rebuild_bm25()
            logger.info("VectorStore: added doc id={} type={}", eid, metadata["type"])

    def update(self, entry: dict, account_id: str = "") -> None:
        with self._lock:
            eid = entry.get("id", "")
            if not eid:
                return
            content = entry.get("content", "")
            metadata = {
                "id": eid,
                "type": entry.get("type", "lesson"),
                "tags": ",".join(entry.get("tags", [])),
                "timestamp": entry.get("timestamp", ""),
                "account_id": account_id,
            }
            self._db.update_document(
                document_id=eid,
                document=Document(page_content=content, metadata=metadata),
            )
            self._rebuild_bm25()

    def delete(self, eid: str) -> None:
        with self._lock:
            self._db.delete(ids=[eid])
            self._rebuild_bm25()

    def clear(self) -> None:
        with self._lock:
            ids = self._db.get()["ids"]
            if ids:
                self._db.delete(ids=ids)
            self._bm25 = None
            self._bm25_ids = []
        logger.info("VectorStore: cleared ({} docs removed)", len(ids))

    def count(self) -> int:
        with self._lock:
            return len(self._db.get()["ids"])

    # ---- Search ----

    def search(self, query: str, max_results: int = 3, min_score: float = 0.2, account_id: str = "") -> list[dict]:
        with self._lock:
            if len(self._db.get()["ids"]) == 0:
                return []
            if self._bm25 is None:
                self._rebuild_bm25()

            if account_id:
                dense_results = self._db.similarity_search_with_score(
                    query, k=max_results * 2, filter={"account_id": account_id}
                )
            else:
                dense_results = self._db.similarity_search_with_score(query, k=max_results * 2)
            bm25_scores = self._bm25_score(query)

        merged: dict[str, dict] = {}
        for doc, distance in dense_results:
            eid = doc.metadata.get("id", "")
            vector_score = max(0.0, 1.0 - distance)
            merged[eid] = {
                "id": eid,
                "content": doc.page_content,
                "type": doc.metadata.get("type", "lesson"),
                "_vector_score": vector_score,
                "_bm25_score": bm25_scores.get(eid, 0.0),
            }

        for eid, bscore in bm25_scores.items():
            if eid in merged:
                merged[eid]["_bm25_score"] = bscore
            else:
                merged[eid] = {
                    "id": eid,
                    "content": "",
                    "type": "lesson",
                    "_vector_score": 0.0,
                    "_bm25_score": bscore,
                }

        bm25_only_ids = [eid for eid, d in merged.items() if not d["content"]]
        if bm25_only_ids:
            try:
                fetched = self._db.get(ids=bm25_only_ids)
                for i, eid in enumerate(fetched["ids"]):
                    docs = fetched.get("documents") or []
                    if i < len(docs) and docs[i]:
                        merged[eid]["content"] = docs[i]
                        meta = (fetched.get("metadatas") or [None])[i]
                        if meta:
                            merged[eid]["type"] = meta.get("type", "lesson")
            except Exception:
                logger.debug("VectorStore: failed to fetch BM25-only docs by ID")

        scored = [(data["_vector_score"] * 0.6 + data["_bm25_score"] * 0.4, data) for data in merged.values()]
        results = [(s, d) for s, d in scored if s >= min_score]
        results.sort(key=lambda x: x[0], reverse=True)
        return [{"id": d["id"], "content": d["content"], "type": d["type"]} for _, d in results[:max_results]]

    def _bm25_score(self, query: str) -> dict[str, float]:
        if self._bm25 is None or not self._bm25_ids:
            return {}
        tokenized = query.lower().split()
        if not tokenized:
            return {}
        raw = self._bm25.get_scores(tokenized)
        scores: dict[str, float] = {}
        if raw.max() > 0:
            normalized = raw / raw.max()
            for i, eid in enumerate(self._bm25_ids):
                scores[eid] = float(min(normalized[i], 1.0))
        return scores

    def _rebuild_bm25(self) -> None:
        all_docs = self._db.get()
        if not all_docs["ids"]:
            self._bm25 = None
            self._bm25_ids = []
            return
        self._bm25_ids = all_docs["ids"]
        documents = all_docs.get("documents") or [""] * len(self._bm25_ids)
        tokenized_corpus = [doc.lower().split() for doc in documents]
        self._bm25 = BM25Okapi(tokenized_corpus)
        logger.info("VectorStore: rebuilt BM25 index ({} docs)", len(self._bm25_ids))
