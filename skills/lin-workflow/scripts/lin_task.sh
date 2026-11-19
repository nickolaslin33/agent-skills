#!/usr/bin/env bash
# lin_task.sh - 任務檢查點：記錄、比對、還原一件任務期間的檔案狀態。
#
# 不可破壞的前提：
# - 快照一律透過暫時的索引檔產生，不得改動使用者的工作目錄、暫存區與目前分支。
# - 檢查點放在 refs/ai-task/ 底下，不能改放 refs/heads/，否則會出現在分支清單並被 push --all 推出去。
# - 還原只用 git apply -R 且不帶 --index，暫存區永遠不動。
# - 需相容 macOS 內建的 bash 3.2，不要使用關聯陣列、mapfile 等較新的語法。
#   bash 3.2 會把緊接在變數後面的中文字當成變數名稱的一部分，這種位置要寫成 ${var}。
set -euo pipefail

REF_NS="refs/ai-task"
MAX_MB="${LIN_TASK_MAX_UNTRACKED_MB:-20}"

die() { echo "lin_task: $*" >&2; exit 1; }

usage() {
  cat <<'EOF'
用法：在要記錄的 git repo 裡執行（每個相關 repo 各執行一次）

  lin_task.sh start    <任務> [說明]            任務開始、第一次寫檔之前記錄起點
  lin_task.sh ckpt     <任務> <標籤> <說明>     記錄一個檢查點
  lin_task.sh list     [任務]                   列出檢查點
  lin_task.sh diff     <任務> [起 [迄]] [-- git diff 的選項]
                                                比對兩個檢查點，預設 start 到目前狀態
  lin_task.sh undo     <任務> <起> <迄>         只還原兩個檢查點之間的修改
  lin_task.sh rollback <任務> [標籤]            退回到某個檢查點，預設 start
  lin_task.sh export   <任務> <標籤> <目錄>     把檢查點的完整檔案匯出到空目錄
  lin_task.sh clean    <任務>                   刪除這件任務的所有檢查點

標籤 now 代表目前的工作目錄狀態。
任務與標籤只能用英數字、點、底線、連字號。

環境變數：
  LIN_TASK_MAX_UNTRACKED_MB   未追蹤檔案的大小上限，預設 20
  LIN_TASK_ALLOW_LARGE=1      略過上述大小檢查
EOF
}

enter_repo() {
  local top
  top=$(git rev-parse --show-toplevel 2>/dev/null) || die "目前目錄不在 git repo 裡"
  # git apply 只處理目前目錄底下的路徑，所以一律回到 repo 根目錄執行
  cd "$top"
}

check_name() {
  case "$1" in
    ''|.*|*..*|*[!A-Za-z0-9._-]*) die "名稱「$1」不合法，只能用英數字、點、底線、連字號" ;;
  esac
}

ref_of() { echo "$REF_NS/$1/$2"; }

# 未追蹤又未被忽略的大檔會被整個寫進 .git 物件庫，所以先擋下來
guard_large() {
  [ "${LIN_TASK_ALLOW_LARGE:-0}" = "1" ] && return 0
  [ -n "$(git ls-files -o --exclude-standard | head -n 1)" ] || return 0
  local limit_kb big
  limit_kb=$((MAX_MB * 1024))
  big=$(git ls-files -o --exclude-standard -z | xargs -0 du -k 2>/dev/null \
        | awk -v l="$limit_kb" '$1 > l { printf "  %d MB  %s\n", $1 / 1024, substr($0, index($0, "\t") + 1) }') || true
  [ -z "$big" ] && return 0
  echo "lin_task: 下列未追蹤檔案超過 ${MAX_MB} MB，快照會把它們寫進 .git：" >&2
  echo "$big" >&2
  die "請先把它們加進 .gitignore 或 .git/info/exclude；確定要納入時設定 LIN_TASK_ALLOW_LARGE=1"
}

# 輸出代表目前工作目錄狀態的 tree 雜湊
snap() {
  local idx tree
  guard_large
  idx=$(mktemp -u "${TMPDIR:-/tmp}/lin-task-index.XXXXXX")
  cp "$(git rev-parse --git-path index)" "$idx" 2>/dev/null || true
  if ! GIT_INDEX_FILE="$idx" git add -A >/dev/null 2>"$idx.err"; then
    cat "$idx.err" >&2
    rm -f "$idx" "$idx.err" "$idx.lock"
    die "無法建立快照"
  fi
  tree=$(GIT_INDEX_FILE="$idx" git write-tree)
  rm -f "$idx" "$idx.err" "$idx.lock"
  echo "$tree"
}

# 用固定身分建立 commit，避免依賴使用者的 git 設定，也不把個人 email 寫進檢查點
make_commit() {
  local tree="$1" msg="$2"
  if git rev-parse -q --verify HEAD >/dev/null 2>&1; then
    GIT_AUTHOR_NAME=lin-task GIT_AUTHOR_EMAIL=lin-task@localhost \
    GIT_COMMITTER_NAME=lin-task GIT_COMMITTER_EMAIL=lin-task@localhost \
      git commit-tree "$tree" -p HEAD -m "$msg"
  else
    GIT_AUTHOR_NAME=lin-task GIT_AUTHOR_EMAIL=lin-task@localhost \
    GIT_COMMITTER_NAME=lin-task GIT_COMMITTER_EMAIL=lin-task@localhost \
      git commit-tree "$tree" -m "$msg"
  fi
}

save_ckpt() {
  local task="$1" label="$2" msg="$3" ref tree
  check_name "$task"; check_name "$label"
  [ "$label" = "now" ] && die "now 是保留字，不能當標籤"
  ref=$(ref_of "$task" "$label")
  git check-ref-format "$ref" || die "名稱不合法：$ref"
  git rev-parse -q --verify "$ref" >/dev/null 2>&1 && die "檢查點 $task/$label 已存在，請換一個標籤"
  tree=$(snap)
  git update-ref "$ref" "$(make_commit "$tree" "$msg")"
  echo "已記錄檢查點 $task/$label"
}

# 把標籤轉成 tree 雜湊；now 代表目前狀態
tree_of() {
  local task="$1" label="$2"
  if [ "$label" = "now" ]; then
    snap
  else
    check_name "$label"
    git rev-parse -q --verify "$(ref_of "$task" "$label")^{tree}" 2>/dev/null \
      || die "找不到檢查點 $task/$label"
  fi
}

# 反向套用 a 到 b 的差異。整段無法乾淨套用時不改動任何檔案。
reverse_apply() {
  local a="$1" b="$2" patch
  patch=$(mktemp "${TMPDIR:-/tmp}/lin-task-patch.XXXXXX")
  git diff --binary --no-ext-diff --no-textconv --no-color \
      --src-prefix=a/ --dst-prefix=b/ "$a" "$b" > "$patch"
  if [ ! -s "$patch" ]; then
    rm -f "$patch"
    echo "兩個狀態之間沒有差異，不需要還原"
    return 0
  fi
  if ! git apply -R --check --whitespace=nowarn "$patch" 2>/dev/null; then
    echo "lin_task: 這段修改無法直接還原，檔案沒有被改動。" >&2
    echo "lin_task: 通常是後來的修改動到同一段程式。差異已存到 ${patch}，請參考它手動還原。" >&2
    exit 2
  fi
  git apply -R --whitespace=nowarn "$patch"
  rm -f "$patch"
}

backup_before() {
  local task="$1" why="$2" label
  label="auto-$(date +%Y%m%d-%H%M%S)-before-$why"
  # 同一秒內連續還原時標籤會重複
  while git rev-parse -q --verify "$(ref_of "$task" "$label")" >/dev/null 2>&1; do
    label="$label-$RANDOM"
  done
  save_ckpt "$task" "$label" "執行 $why 之前自動記錄" >/dev/null
  echo "還原前的狀態已記錄為 $task/$label"
}

cmd_start() {
  [ $# -ge 1 ] || die "用法：start <任務> [說明]"
  local task="$1" msg="${2:-任務開始}"
  save_ckpt "$task" start "$msg"
  echo "repo：$(pwd)"
  echo "分支：$(git symbolic-ref -q --short HEAD || echo '(detached)')  HEAD：$(git rev-parse -q --short HEAD 2>/dev/null || echo '(尚無 commit)')"
  echo "開工前已有的未提交變更：$(git status --porcelain | wc -l | tr -d ' ') 個檔案"
}

cmd_ckpt() {
  [ $# -eq 3 ] || die "用法：ckpt <任務> <標籤> <說明>"
  save_ckpt "$1" "$2" "$3"
}

cmd_list() {
  local prefix="$REF_NS/"
  if [ $# -ge 1 ]; then check_name "$1"; prefix="$REF_NS/$1/"; fi
  git for-each-ref --sort=creatordate "$prefix" \
    --format='%(refname:lstrip=2)	%(creatordate:format:%m-%d %H:%M)	%(subject)'
}

cmd_diff() {
  [ $# -ge 1 ] || die "用法：diff <任務> [起 [迄]] [-- git diff 的選項]"
  local task="$1" from="start" to="now" a b
  shift; check_name "$task"
  if [ $# -ge 1 ] && [ "$1" != "--" ]; then from="$1"; shift; fi
  if [ $# -ge 1 ] && [ "$1" != "--" ]; then to="$1"; shift; fi
  if [ $# -ge 1 ] && [ "$1" = "--" ]; then shift; fi
  a=$(tree_of "$task" "$from"); b=$(tree_of "$task" "$to")
  git --no-pager diff "$@" "$a" "$b"
}

cmd_undo() {
  [ $# -eq 3 ] || die "用法：undo <任務> <起> <迄>"
  local task="$1" a b
  check_name "$task"
  a=$(tree_of "$task" "$2"); b=$(tree_of "$task" "$3")
  backup_before "$task" undo
  reverse_apply "$a" "$b"
  echo "已還原 $task/$2 到 $task/$3 之間的修改"
}

cmd_rollback() {
  [ $# -ge 1 ] || die "用法：rollback <任務> [標籤]"
  local task="$1" label="${2:-start}" a b
  check_name "$task"
  a=$(tree_of "$task" "$label")
  backup_before "$task" rollback
  b=$(snap)
  reverse_apply "$a" "$b"
  echo "已退回到檢查點 $task/$label"
}

cmd_export() {
  [ $# -eq 3 ] || die "用法：export <任務> <標籤> <目錄>"
  local task="$1" label="$2" dir="$3" tree
  check_name "$task"
  tree=$(tree_of "$task" "$label")
  mkdir -p "$dir"
  [ -z "$(ls -A "$dir")" ] || die "目錄 $dir 不是空的"
  git archive "$tree" | tar -x -C "$dir"
  echo "已把 $task/$label 匯出到 $dir"
}

cmd_clean() {
  [ $# -eq 1 ] || die "用法：clean <任務>"
  local task="$1" n
  check_name "$task"
  n=$(git for-each-ref "$REF_NS/$task/" | wc -l | tr -d ' ')
  git for-each-ref "$REF_NS/$task/" --format='delete %(refname)' | git update-ref --stdin
  echo "已刪除 $task 的 $n 個檢查點"
}

main() {
  [ $# -ge 1 ] || { usage; exit 1; }
  local cmd="$1"; shift
  case "$cmd" in
    -h|--help|help) usage; exit 0 ;;
  esac
  enter_repo
  case "$cmd" in
    start)    cmd_start "$@" ;;
    ckpt)     cmd_ckpt "$@" ;;
    list)     cmd_list "$@" ;;
    diff)     cmd_diff "$@" ;;
    undo)     cmd_undo "$@" ;;
    rollback) cmd_rollback "$@" ;;
    export)   cmd_export "$@" ;;
    clean)    cmd_clean "$@" ;;
    *)        usage; die "不認得的指令：$cmd" ;;
  esac
}

main "$@"
