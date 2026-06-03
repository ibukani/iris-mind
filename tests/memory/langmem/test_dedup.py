"""Dedup / hash helper に関するテスト。"""

from __future__ import annotations

import pytest

from iris.memory.langmem.dedup import (
    compute_candidate_hash,
    compute_payload_signature,
    normalize_string,
)

pytestmark = pytest.mark.legacy


def test_compute_payload_signature_is_key_order_independent() -> None:
    a = {"content": "ユーザーは Rust を好む", "evidence": "発言"}
    b = {"evidence": "発言", "content": "ユーザーは Rust を好む"}
    assert compute_payload_signature(a) == compute_payload_signature(b)


def test_compute_payload_signature_trims_strings() -> None:
    a = {"content": "  trim me  ", "evidence": "x"}
    b = {"content": "trim me", "evidence": "x"}
    assert compute_payload_signature(a) == compute_payload_signature(b)


def test_compute_payload_signature_ignores_volatile_top_level() -> None:
    a = {"content": "hi", "id": "abc"}
    b = {"content": "hi", "id": "def"}
    assert compute_payload_signature(a) == compute_payload_signature(b)


def test_compute_candidate_hash_differs_by_target_store() -> None:
    payload = {"content": "x", "evidence": "y", "confidence": 0.9}
    h1 = compute_candidate_hash(target_store="semantic", payload=payload, account_id="a", room_id="r")
    h2 = compute_candidate_hash(target_store="style", payload=payload, account_id="a", room_id="r")
    assert h1 != h2


def test_compute_candidate_hash_differs_by_scope() -> None:
    payload = {"content": "x", "evidence": "y", "confidence": 0.9}
    h1 = compute_candidate_hash(target_store="semantic", payload=payload, account_id="a", room_id="r")
    h2 = compute_candidate_hash(target_store="semantic", payload=payload, account_id="b", room_id="r")
    h3 = compute_candidate_hash(target_store="semantic", payload=payload, account_id="a", room_id="r2")
    assert h1 != h2
    assert h1 != h3


def test_compute_candidate_hash_different_payload_different_hash() -> None:
    h1 = compute_candidate_hash(
        target_store="semantic",
        payload={"content": "A", "evidence": "e", "confidence": 0.9},
        account_id="a",
        room_id="r",
    )
    h2 = compute_candidate_hash(
        target_store="semantic",
        payload={"content": "B", "evidence": "e", "confidence": 0.9},
        account_id="a",
        room_id="r",
    )
    assert h1 != h2


def test_normalize_string_handles_non_string() -> None:
    assert normalize_string(123) == "123"
    assert normalize_string(None) == ""
    assert normalize_string("  hi  ") == "hi"


def test_hash_is_hex_sha256() -> None:
    h = compute_candidate_hash(target_store="semantic", payload={"content": "x"})
    assert len(h) == 64
    int(h, 16)  # parses as hex


@pytest.mark.parametrize(
    ("payload_a", "payload_b", "expected_equal"),
    [
        ({"content": "x"}, {"content": "x"}, True),
        ({"content": "  x  "}, {"content": "x"}, True),
        ({"content": "x", "id": "1"}, {"content": "x", "id": "2"}, True),
        ({"content": "x", "extra": 1}, {"content": "x"}, False),
        ({"content": "x"}, {"content": "y"}, False),
    ],
)
def test_compute_payload_signature_table(payload_a, payload_b, expected_equal) -> None:
    if expected_equal:
        assert compute_payload_signature(payload_a) == compute_payload_signature(payload_b)
    else:
        assert compute_payload_signature(payload_a) != compute_payload_signature(payload_b)
