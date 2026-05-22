from __future__ import annotations

import math
import threading
from typing import cast

from loguru import logger


class VectorStore:
    """ChromaDB + BM25 ハイブリッド検索エンジン"""

    def __init__(self, path: str = ".iris/data/chroma_db"):
        import chromadb
        from chromadb.utils import embedding_functions as ef

        self.client = chromadb.PersistentClient(path=path)
        self.dense_ef = cast(chromadb.EmbeddingFunction, ef.ONNXMiniLM_L6_V2())
        self.collection = self.client.get_or_create_collection(
            name="semantic",
            embedding_function=self.dense_ef,
            metadata={"hnsw:space": "cosine"},
        )
        self._all_docs: dict[str, str] = {}
        self._doc_lengths: dict[str, int] = {}
        self._inverted_index: dict[str, dict[str, int]] = {}
        self._bm25_doc_freq: dict[str, int] = {}
        self._avgdl: float = 1.0
        self._bm25_dirty = True
        self._lock = threading.Lock()

    def add(self, entry: dict) -> None:
        with self._lock:
            eid = entry.get("id", str(hash(entry.get("content", ""))))
            content = entry.get("content", "")
            metadata = {
                "type": entry.get("type", "lesson"),
                "tags": ",".join(entry.get("tags", [])),
                "timestamp": entry.get("timestamp", ""),
            }
            self.collection.add(
                ids=[eid],
                documents=[content],
                metadatas=[metadata],
            )
            self._bm25_dirty = True
            logger.info("VectorStore: added doc id=%s type=%s", eid, metadata["type"])

    def update(self, entry: dict) -> None:
        with self._lock:
            eid = entry.get("id", "")
            if not eid:
                return
            content = entry.get("content", "")
            metadata = {
                "type": entry.get("type", "lesson"),
                "tags": ",".join(entry.get("tags", [])),
                "timestamp": entry.get("timestamp", ""),
            }
            self.collection.update(
                ids=[eid],
                documents=[content],
                metadatas=[metadata],
            )
            self._bm25_dirty = True

    def delete(self, eid: str) -> None:
        with self._lock:
            self.collection.delete(ids=[eid])

    def clear(self) -> None:
        with self._lock:
            all_ids = self.collection.get()["ids"]
            if all_ids:
                self.collection.delete(ids=all_ids)
            self._all_docs = {}
            self._doc_lengths = {}
            self._inverted_index = {}
            self._bm25_doc_freq = {}
            self._avgdl = 1.0
            self._bm25_dirty = True
        logger.info("VectorStore: cleared (%d docs removed)", len(all_ids))

    def count(self) -> int:
        with self._lock:
            return self.collection.count()  # type: ignore[no-any-return]

    def search(self, query: str, max_results: int = 3, min_score: float = 0.2) -> list[dict]:
        with self._lock:
            if self.collection.count() == 0:
                return []
            if self._bm25_dirty:
                self._rebuild_bm25()
            dense_results = self.collection.query(
                query_texts=[query],
                n_results=max_results * 2,
            )
            bm25_scores = self._bm25_search(query)
        merged: dict[str, dict] = {}
        if dense_results["ids"]:
            docs = dense_results["documents"]
            metas = dense_results["metadatas"]
            dists = dense_results["distances"]
            for i, eid in enumerate(dense_results["ids"][0]):
                distance = dists[0][i] if dists else 0.0
                vector_score = max(0.0, 1.0 - distance)
                merged[eid] = {
                    "id": eid,
                    "content": docs[0][i] if docs else "",
                    "type": ((metas[0][i] or {}) if metas else {}).get("type", "lesson"),
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
        scored = []
        for data in merged.values():
            hybrid = data["_vector_score"] * 0.6 + data["_bm25_score"] * 0.4
            if hybrid >= min_score:
                scored.append((hybrid, data))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [{"id": s["id"], "content": s["content"], "type": s["type"]} for _, s in scored[:max_results]]

    def _bm25_search(self, query: str) -> dict[str, float]:
        if self._bm25_dirty:
            self._rebuild_bm25()
        query_terms = query.lower().split()
        if not query_terms:
            return {}
        n = len(self._all_docs)
        if n == 0:
            return {}
        k1, b = 1.5, 0.75
        scores: dict[str, float] = {}
        for qt in query_terms:
            if qt not in self._inverted_index:
                continue
            idf = math.log((n - self._bm25_doc_freq.get(qt, 0) + 0.5) / (self._bm25_doc_freq.get(qt, 0) + 0.5) + 1)
            for eid, tf in self._inverted_index[qt].items():
                dl = self._doc_lengths[eid]
                s = idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / self._avgdl))
                scores[eid] = scores.get(eid, 0.0) + s
        return {eid: min(score / 10.0, 1.0) for eid, score in scores.items()}

    def _rebuild_bm25(self) -> None:
        if self.collection.count() == 0:
            self._all_docs = {}
            self._doc_lengths = {}
            self._inverted_index = {}
            self._bm25_doc_freq = {}
            self._avgdl = 1.0
            self._bm25_dirty = False
            return
        results = self.collection.get()
        doc_ids = results["ids"]
        documents = results["documents"] or [""] * len(doc_ids)
        self._all_docs = dict(zip(doc_ids, documents, strict=False))
        self._inverted_index = {}
        self._bm25_doc_freq = {}
        total_terms = 0
        for eid, doc in self._all_docs.items():
            terms = doc.lower().split()
            dl = len(terms)
            self._doc_lengths[eid] = dl
            total_terms += dl
            seen = set()
            for t in terms:
                if t not in self._inverted_index:
                    self._inverted_index[t] = {}
                self._inverted_index[t][eid] = self._inverted_index[t].get(eid, 0) + 1
                if t not in seen:
                    self._bm25_doc_freq[t] = self._bm25_doc_freq.get(t, 0) + 1
                    seen.add(t)
        self._avgdl = total_terms / len(self._all_docs)
        self._bm25_dirty = False
        logger.info("VectorStore: rebuilt BM25 index (%d docs)", len(self._all_docs))
