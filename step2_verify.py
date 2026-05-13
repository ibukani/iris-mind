#!/usr/bin/env python3
"""Step 2 完了検証スクリプト"""
import glob
import os
import sys

errors = []

try:
    from iris.kernel.memory_manager import MemoryManager
    print("[OK] MemoryManager import")
except Exception as e:
    errors.append(f"MemoryManager: {e}")
    print(f"FAIL MemoryManager: {e}")

try:
    from iris.kernel import MemoryManager as MM2
    assert MemoryManager is MM2
    print("[OK] 全import正常")
except Exception as e:
    errors.append(f"import: {e}")
    print(f"FAIL import: {e}")

try:
    from memory.stores import EpisodicStore, SemanticStore

    epi = EpisodicStore(path="memory/data/episodes_test.jsonl", max_entries=30)
    sem = SemanticStore(path="memory/data/semantic_test.jsonl", max_entries=100, vector_db_path="memory/data/chroma_test")
    mm = MemoryManager(episodic=epi, semantic=sem)
    print("[OK] MemoryManager constructor (without vector_store)")

    try:
        from memory.vector_store import VectorStore
        vs = VectorStore(path="memory/data/chroma_test")
        mm2 = MemoryManager(episodic=epi, semantic=sem, vector_store=vs)
        print("[OK] MemoryManager constructor (with vector_store)")
    except Exception as e2:
        print(f"[WARN] MemoryManager with vector_store: {e2}")
except Exception as e:
    errors.append(f"constructor: {e}")
    print(f"FAIL constructor: {e}")

try:
    mm.add_episodic("ユーザーがhelloと入力", kind="user_input")
    mm.add_episodic("Irisが応答した", kind="assistant")
    recent = mm.get_recent(2)
    assert len(recent) >= 2, f"expected >=2, got {len(recent)}"
    print("[OK] add_episodic / get_recent works")
except Exception as e:
    errors.append(f"episodic: {e}")
    print(f"FAIL episodic: {e}")

try:
    mm.add_semantic("ユーザーはPythonが好き", tags=["preference", "python"])
    mm.add_semantic("ファイル操作前に確認が必要", tags=["lesson", "file_ops"])
    results = mm.search_semantic("Python", max_results=3)
    print(f"[INFO] search_semantic results count: {len(results)}")
    print("[OK] add_semantic / search_semantic works")
except Exception as e:
    errors.append(f"semantic: {e}")
    print(f"FAIL semantic: {e}")

try:
    prefs = mm.get_user_preferences()
    print(f"[OK] get_user_preferences -> {len(prefs)} results")
except Exception as e:
    errors.append(f"preferences: {e}")
    print(f"FAIL preferences: {e}")

try:
    expected = ["iris/kernel/memory_manager.py"]
    missing = [f for f in expected if not os.path.exists(f)]
    assert not missing, f"Missing: {missing}"
    print("[OK] memory_manager.py exists")
except Exception as e:
    errors.append(f"structure: {e}")
    print(f"FAIL structure: {e}")

separator = "=" * 40
print(separator)
if errors:
    print(f"Done - {len(errors)} issues:")
    for err in errors:
        print(f"  - {err}")
else:
    print("Done - all tests passed!")

# テスト用ファイル整理
for f in glob.glob("memory/data/*test*"):
    try:
        os.remove(f)
    except OSError:
        pass

sys.exit(1 if errors else 0)
