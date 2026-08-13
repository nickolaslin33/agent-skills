# 理解債 — deploy-cli

- [ ] 為什麼備份要在 load 失敗時做，而不是每次 save 前？
      commit: a3f9c21
      added: 2026-08-07
- [ ] ensure_config_dir 為什麼要吞掉 FileExistsError 而不是先檢查？
      commit: a3f9c21
      added: 2026-08-07
- [x] 為什麼 AppConfig 用 dataclass 而不是 dict？
      commit: 8b2e104
      added: 2026-08-01
