from __future__ import annotations
from pathlib import Path
from typing import Any
import math

import chromadb
from chromadb.utils import embedding_functions


class VectorStore:
    """ChromaDB + BM25 ハイブリッド検索エンジン"""

    def __init__(self, path: str = "memory/chroma_db"):
        self.client = chromadb.PersistentClient(path=path)
        self.dense_ef = embedding_functions.ONNXMiniLM_L6_V2()
        self.collection = self.client.get_or_create_collection(
            name="semantic",
            embedding_function=self.dense_ef,
            metadata={"hnsw:space": "cosine"},
        )
        self._bm25_index: dict[str, float] = {}
        self._bm25_dirty = True

    def add(self, entry: dict):
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

    def update(self, entry: dict):
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

    def delete(self, eid: str):
        self.collection.delete(ids=[eid])

    def count(self) -> int:
        return self.collection.count()

    def search(self, query: str, max_results: int = 3, min_score: float = 0.2) -> list[dict]:
        if self.collection.count() == 0:
            return []

        dense_results = self.collection.query(
            query_texts=[query],
            n_results=max_results * 2,
        )

        bm25_scores = self._bm25_search(query)

        merged: dict[str, dict] = {}
        if dense_results["ids"]:
            for i, eid in enumerate(dense_results["ids"][0]):
                distance = dense_results["distances"][0][i]
                vector_score = max(0.0, 1.0 - distance)
                merged[eid] = {
                    "id": eid,
                    "content": dense_results["documents"][0][i],
                    "type": (dense_results["metadatas"][0][i] or {}).get("type", "lesson"),
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

        return [
            {"id": s["id"], "content": s["content"], "type": s["type"]}
            for _, s in scored[:max_results]
        ]

    def _bm25_search(self, query: str) -> dict[str, float]:
        if self._bm25_dirty:
            self._rebuild_bm25()

        query_terms = query.lower().split()
        if not query_terms:
            return {}

        N = self.collection.count()
        if N == 0:
            return {}

        avgdl = sum(
            len(doc.split()) for doc in self._all_docs.values()
        ) / N if self._all_docs else 1.0

        scores: dict[str, float] = {}
        k1, b = 1.5, 0.75

        for eid, doc in self._all_docs.items():
            doc_terms = doc.lower().split()
            dl = len(doc_terms)
            score = 0.0
            for qt in query_terms:
                tf = doc_terms.count(qt)
                if tf == 0:
                    continue
                idf = math.log((N - self._bm25_doc_freq.get(qt, 0) + 0.5) / (self._bm25_doc_freq.get(qt, 0) + 0.5) + 1)
                score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avgdl))
            if score > 0:
                scores[eid] = min(score / 10.0, 1.0)

        return scores

    def _rebuild_bm25(self):
        if self.collection.count() == 0:
            self._all_docs = {}
            self._bm25_doc_freq = {}
            self._bm25_dirty = False
            return

        results = self.collection.get()
        self._all_docs = dict(zip(results["ids"], results["documents"]))
        self._bm25_doc_freq = {}
        for doc in self._all_docs.values():
            seen = set()
            for t in doc.lower().split():
                if t not in seen:
                    self._bm25_doc_freq[t] = self._bm25_doc_freq.get(t, 0) + 1
                    seen.add(t)
        self._bm25_dirty = False
