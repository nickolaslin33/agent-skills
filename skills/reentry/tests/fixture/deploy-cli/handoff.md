---
project: deploy-cli
updated: 2026-08-07T23:14:05+08:00
warning: 這批產出你基本沒吸收，四項裡三項跟事實對不上。
---

## 我叫它做什麼，做到哪裡
把 ConfigStore 的 load/save 寫完，備份邏輯還沒接上。

## 下一步
實作設定檔損毀時的重建流程，改完跑 `pytest tests/test_config.py`

## 關鍵詞
ConfigStore, JSON 損毀備份, ensure_config_dir

## 不確定的地方
不確定損毀時該備份舊檔還是直接重建

## 我當初記錯的
- 我寫「測試全過」，實際是 14 passed / 2 failed
- 我說備份寫在 save 裡，實際在 load 的例外處理
