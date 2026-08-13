---
project: orders-api
date: 2026-08-10
promoted: false
---

## 決定
migration 版本記在 DB 的 schema_migration 表，不靠檔名排序。

## 排除了什麼
只靠檔名排序——手動改過檔名或補插一份舊 migration 就會重複套用。

## 後續 todo
- 補 `tests/store/test_migration.py`，測重跑不會重複套用

## 技術債
（無）
