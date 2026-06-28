#!/usr/bin/env bash
# shellcheck disable=SC2250,SC2016
# SC2250: jq クエリ内の $u/$b/$state を bash 変数として誤検知し brace 化を強制するため無効化
# SC2016: jq の文字列補間 \($u) を含む single-quoted 文字列を意図的に使用するため無効化
# review-resolve スキル用のステータス取得ヘルパー
# 使い方: source このスクリプト, または直接サブコマンドで実行
#   $ bash review-resolve-status.sh <subcommand> <args>
#
# サブコマンド:
#   init                       OWNER/REPO/N/MY_LOGIN/LAST_PUSH_TS を echo (env 設定用)
#   unresolved-threads         未解決 reviewThread を JSON 行で列挙
#   outside-diff-reviews       「Outside diff range」を含む review を JSON 行で列挙
#   react PR_COMMENT_ID +1|-1  PR review comment にリアクションを付ける
#   resolve THREAD_NODE_ID     reviewThread を resolved にする
#   walkthrough-id             CodeRabbit walkthrough コメントの databaseId を返す
#   walkthrough-state          walkthrough の現在状態を1行で出す
#                              形式: updated_at=<iso> state=<in_progress|rate_limited|no_actionable|has_actionable|unknown>
#   walkthrough-history        walkthrough の編集履歴をマーカー分類付きで列挙
#   coderabbit-trigger         '@coderabbit review' を投稿し comment ID と時刻を出す
#   bot-reviews-since TS       TS 以降の bot review を列挙 (login/submitted/id)
#   codex-reaction             Codex の PR-issue リアクションを列挙 (eyes/+1/-1)
#   completion-summary         未解決スレッド数と各 bot シグナルの現在値を1ブロックで出す
#
# 設計: review-resolve.md の検知ロジックを全てここに集約し、skill 本体は
# 自然言語の判断手順だけに専念する。jq クエリの重複と「自然言語ながら定型」
# な指示を排除する。

set -uo pipefail

owner_repo_n() {
  : "${OWNER:?OWNER not set; run 'review-resolve-status.sh init' first}"
  : "${REPO:?REPO not set}"
  : "${N:?N not set}"
}

cmd_init() {
  local n login owner repo last_push
  n=$(gh pr view --json number --jq .number)
  login=$(gh api user --jq .login)
  read -r owner repo <<< "$(gh repo view --json owner,name --jq '"\(.owner.login) \(.name)"')"
  last_push=$(gh pr view "$n" --json commits --jq '.commits[-1].committedDate')
  printf 'export OWNER=%q REPO=%q N=%q MY_LOGIN=%q LAST_PUSH_TS=%q\n' "$owner" "$repo" "$n" "$login" "$last_push"
}

cmd_unresolved_threads() {
  owner_repo_n
  gh api graphql -f query="query { repository(owner: \"$OWNER\", name: \"$REPO\") { pullRequest(number: $N) { reviewThreads(first: 50) { nodes { id isResolved path line comments(first: 5) { nodes { author { login } databaseId createdAt body } } } } } } }" \
    --jq '.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false)'
}

cmd_outside_diff_reviews() {
  owner_repo_n
  gh api "repos/$OWNER/$REPO/pulls/$N/reviews" --paginate \
    --jq '.[] | select(.body != null and (.body | test("(?i)outside (?:the )?diff range"))) | {id: .id, user: .user.login, submitted: .submitted_at, body: .body}'
}

cmd_react() {
  owner_repo_n
  local cid="${1:?need PR review comment ID}" content="${2:?need +1 or -1}"
  gh api -X POST "repos/$OWNER/$REPO/pulls/comments/$cid/reactions" -f "content=$content" --jq '.content'
}

cmd_resolve() {
  local node_id="${1:?need thread node ID}"
  gh api graphql -f query="mutation { resolveReviewThread(input: { threadId: \"$node_id\" }) { thread { isResolved } } }" \
    --jq '.data.resolveReviewThread.thread.isResolved'
}

cmd_walkthrough_id() {
  owner_repo_n
  gh api "repos/$OWNER/$REPO/issues/$N/comments" --paginate \
    --jq '.[] | select(.user.login == "coderabbitai[bot]") | select(.body | startswith("<!-- This is an auto-generated comment: summarize by coderabbit.ai -->")) | .id' | head -1
}

cmd_walkthrough_state() {
  owner_repo_n
  local wid
  wid=$(cmd_walkthrough_id)
  [ -z "$wid" ] && {
    echo "updated_at=none state=no_walkthrough"
    return
  }
  gh api "repos/$OWNER/$REPO/issues/comments/$wid" --jq '
    .updated_at as $u
    | .body as $b
    | (if ($b | contains("review in progress by coderabbit.ai")) then "in_progress"
       elif ($b | contains("Actionable comments posted: 0")) then "no_actionable"
       elif ($b | test("Actionable comments posted: [1-9]")) then "has_actionable"
       elif ($b | contains("No actionable comments were generated")) then "no_actionable"
       else "unknown" end) as $state
    | "updated_at=\($u) state=\($state)"'
}

cmd_walkthrough_history() {
  owner_repo_n
  local wid node_id
  wid=$(cmd_walkthrough_id)
  [ -z "$wid" ] && {
    echo "no walkthrough"
    return
  }
  node_id=$(gh api "repos/$OWNER/$REPO/issues/comments/$wid" --jq '.node_id')
  gh api graphql -f query="query { node(id: \"$node_id\") { ... on IssueComment { userContentEdits(first: 100) { nodes { editedAt diff } } } } }" \
    --jq '.data.node.userContentEdits.nodes[] | {
      editedAt,
      in_progress: (.diff | contains("review in progress by coderabbit.ai")),
      rate_limited_marker: (.diff | contains("rate limited by coderabbit.ai")),
      has_actionable_phrase: (.diff | (contains("No actionable comments were generated") or test("Actionable comments posted: [0-9]+")))
    }'
}

cmd_coderabbit_trigger() {
  owner_repo_n
  local cid ts
  cid=$(gh api "repos/$OWNER/$REPO/issues/$N/comments" -f body="@coderabbit review" --jq '.id')
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  echo "comment_id=$cid posted_at=$ts"
}

cmd_bot_reviews_since() {
  owner_repo_n
  local since="${1:?need timestamp ISO8601}"
  gh api "repos/$OWNER/$REPO/pulls/$N/reviews" --paginate \
    --jq ".[] | select(.user.login | endswith(\"[bot]\")) | select(.submitted_at > \"$since\") | \"\(.user.login) submitted_at=\(.submitted_at) id=\(.id)\""
}

cmd_codex_reaction() {
  owner_repo_n
  gh api "repos/$OWNER/$REPO/issues/$N/reactions" \
    --jq '.[] | select(.user.login == "chatgpt-codex-connector[bot]") | "\(.content) at \(.created_at)"'
}

cmd_completion_summary() {
  owner_repo_n
  echo "--- unresolved threads ---"
  cmd_unresolved_threads | jq -r 'select(.isResolved == false) | "\(.path):\(.line) cid=\(.comments.nodes[0].databaseId) author=\(.comments.nodes[0].author.login)"' || echo "(none)"
  echo "--- codex reactions ---"
  cmd_codex_reaction || echo "(none)"
  echo "--- coderabbit walkthrough state ---"
  cmd_walkthrough_state || echo "(none)"
}

main() {
  local sub="${1:-}"
  shift || true
  case "$sub" in
    init) cmd_init "$@" ;;
    unresolved-threads) cmd_unresolved_threads "$@" ;;
    outside-diff-reviews) cmd_outside_diff_reviews "$@" ;;
    react) cmd_react "$@" ;;
    resolve) cmd_resolve "$@" ;;
    walkthrough-id) cmd_walkthrough_id "$@" ;;
    walkthrough-state) cmd_walkthrough_state "$@" ;;
    walkthrough-history) cmd_walkthrough_history "$@" ;;
    coderabbit-trigger) cmd_coderabbit_trigger "$@" ;;
    bot-reviews-since) cmd_bot_reviews_since "$@" ;;
    codex-reaction) cmd_codex_reaction "$@" ;;
    completion-summary) cmd_completion_summary "$@" ;;
    "" | help | -h | --help)
      sed -n '2,40p' "$0"
      ;;
    *)
      echo "unknown subcommand: $sub" >&2
      exit 2
      ;;
  esac
}

main "$@"
