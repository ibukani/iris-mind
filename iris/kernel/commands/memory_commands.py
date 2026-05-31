from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.memory.manager import MemoryManager


class MemoryCommands:
    def __init__(self, memory: MemoryManager | None = None) -> None:
        self._memory = memory

    def set_memory(self, memory: MemoryManager) -> None:
        self._memory = memory

    @staticmethod
    def _extract_room_id(args: str) -> tuple[str, str]:
        room_id = ""
        rest = args
        for token in args.split():
            if token.startswith("room:"):
                room_id = token[5:]
                rest = rest.replace(token, "", 1)
                break
        return room_id, rest

    def handle(self, args: str) -> str:
        if not self._memory:
            return "Memory not available"
        room_id, rest = self._extract_room_id(args)
        parts = rest.strip().split(maxsplit=1)
        sub = parts[0].lower() if parts else ""
        if sub == "recent":
            n_str = parts[1] if len(parts) > 1 else "5"
            try:
                n = max(1, int(n_str))
            except ValueError:
                n = 5
            return self._recent(n, room_id)
        if sub == "search":
            query = parts[1] if len(parts) > 1 else ""
            if not query:
                return "Usage: /memory search <query>"
            return self._search(query, room_id)
        if sub == "clear":
            stream = parts[1].lower() if len(parts) > 1 else ""
            return self._clear(stream)
        return self._stats()

    def _recent(self, n: int, room_id: str = "") -> str:
        if not self._memory:
            return "Memory not available"
        entries = self._memory.retrieve("episodic", n=n, room_id=room_id)
        if not entries:
            return "No episodic memories"
        lines = [f"Recent {len(entries)} episodic memories:"]
        for i, e in enumerate(entries, 1):
            summary = e.get("summary", "")[:120]
            ts = e.get("timestamp", "")[:19]
            lines.append(f"  {i}. [{ts}] {summary}")
        return "\n".join(lines)

    def _search(self, query: str, room_id: str = "") -> str:
        if not self._memory:
            return "Memory not available"
        results = self._memory.search(query, stream="semantic", max_results=5, room_id=room_id)
        if not results:
            return f"No results for: {query}"
        lines = [f"Search results for '{query}':"]
        for r in results:
            content = r.get("content", "")[:120]
            score = r.get("score", 0)
            lines.append(f"  [{score:.2f}] {content}")
        return "\n".join(lines)

    def _clear(self, stream: str) -> str:
        if not self._memory:
            return "Memory not available"
        valid = {"", "episodic", "semantic"}
        if stream not in valid:
            return "Usage: /memory clear [episodic|semantic]"
        s: str | None = stream if stream else None
        self._memory.clear(s)
        return f"Cleared {stream or 'all'} memory"

    def _stats(self) -> str:
        if not self._memory:
            return "Memory not available"
        lines = ["Memory stats:"]
        if self._memory.long_term.episodic:
            entries = self._memory.long_term.episodic.load_all()
            lines.append(f"  Episodic: {len(entries)} entries")
        if self._memory.long_term.semantic:
            entries = self._memory.long_term.semantic.load_all()
            lines.append(f"  Semantic: {len(entries)} entries")
        return "\n".join(lines)
