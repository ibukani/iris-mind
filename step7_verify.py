"""
Step 7 検証スクリプト — Reflexion
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from iris.kernel.reflexion import Reflexion

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        msg = f"  FAIL: {name}"
        if detail:
            msg += f" - {detail}"
        print(msg)


# ── Test 1: Constructor ─────────────────────────────────
print("\n=== Test 1: Constructor ===")
r = Reflexion(llm=object())
check("Reflexion created", r is not None)
check("llm stored", r.llm is not None)


# ── Test 2: Empty reflect ───────────────────────────────
print("\n=== Test 2: Empty reflect ===")
result = r.reflect([])
check("returns dict", isinstance(result, dict))
check("summary empty", result["summary"] == "")
check("contains all keys", set(result.keys()) == {
    "summary", "lesson", "preference", "improvement",
    "missing_capability", "speech_style", "expressed_traits",
    "user_reaction",
})

result2 = r.reflect([{"role": "user", "content": "hi"}])
check("single message returns empty", result2["summary"] == "")


# ── Test 3: Empty quick_reflect ─────────────────────────
print("\n=== Test 3: Empty quick_reflect ===")
qr = r.quick_reflect([])
check("returns dict", isinstance(qr, dict))
check("3 keys only", set(qr.keys()) == {"speech_style", "expressed_traits", "user_reaction"})
check("speech_style empty", qr["speech_style"] == "")


# ── Test 4: should_add_capability ───────────────────────
print("\n=== Test 4: should_add_capability ===")
check("empty returns False", not Reflexion.should_add_capability({"missing_capability": ""}))
check("non-empty returns True", Reflexion.should_add_capability({"missing_capability": "file_search"}))
check("missing key returns False", not Reflexion.should_add_capability({}))


# ── Test 5: _empty_reflect ──────────────────────────────
print("\n=== Test 5: _empty_reflect ===")
e = Reflexion._empty_reflect()
check("all empty strings", all(v == "" for v in e.values()))
check("8 keys", len(e) == 8)


# ── Summary ─────────────────────────────────────────────
print(f"\n{'='*40}")
print(f"Results: {passed} passed, {failed} failed")
if failed:
    sys.exit(1)
else:
    print("All tests passed!")
