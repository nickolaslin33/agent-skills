---
project: deploy-cli
generated: 2026-08-07T23:16:41+08:00
---

## 改了什麼
改了 1 個設定存取檔與 pyproject，新增 1 個測試檔。
動到的是 ConfigStore 的 load/save，那是設定這條路徑的入口。

## 驗證
pytest 14 passed / 2 failed

## 明細
改了 3 個檔（+119 −4）
src/stock_tui/config/store.py  +82 −4
tests/test_config.py           新增 +36
pyproject.toml                 +1 −0
比較基準：工作區未提交的變更（對 HEAD a3f9c21）
