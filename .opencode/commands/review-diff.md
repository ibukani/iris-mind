---
description: 現在の差分をレビューする。原則コード変更は禁止。
---

@reviewer

現在の差分をレビューしてください。

## 観点

- 変更範囲は妥当か
- layer boundary は守られているか
- provider 固有処理が上位層に漏れていないか
- protobuf 依存が domain に漏れていないか
- manager / gateway / orchestrator が肥大化していないか
- 不要な互換層や dead code がないか
- テストは十分か
- 検証結果は正直に報告されているか
