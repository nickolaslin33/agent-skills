---
project: orders-api
generated: 2026-08-10T18:03:55+08:00
---

## 改了什麼
新增 migration runner 與第一份 schema，store 這層有表結構了

## 驗證
pytest 8 passed

## 明細
改了 2 個檔（+188 −0）
orders-api/store/migration.py   新增 +48
orders-api/store/0001_init.sql  +140 −0
比較基準：工作區未提交的變更（對 HEAD 4c81d33）
