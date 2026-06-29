#!/usr/bin/env bash
# shellcheck disable=SC2250,SC2016
# SC2250: jq クエリ内の $u/$b/$state を bash 変数として誤検知し brace 化を強制するため無効化
# SC2016: jq の文字列補間 \($u) を含む single-quoted 文字列を意図的に使用するため無効化
# review-resolve スキル用のステータス取得ヘルパー
# 使い方: 直接サブコマンドで実行する (source による取り込みは想定しない)
#   $ bash review-resolve-status.sh <subcommand> <args>
#
# サブコマンド:
#   init                       OWNER/REPO/N/MY_LOGIN/LAST_PUSH_TS を echo (env 設定用)
#   unresolved-threads         未解決 reviewThread を JSON 行で列挙 (pagination 対応)
#   outside-diff-reviews       「Outside diff range」を含む review を JSON 行で列挙
#   react PR_COMMENT_ID +1|-1  PR review comment にリアクションを付ける
#   resolve THREAD_NODE_ID     reviewThread を resolved にする
#   walkthrough-id             CodeRabbit walkthrough コメント (最新) の databaseId を返す
#   walkthrough-state          walkthrough の現在状態を1行で出す
#                              形式: updated_at=<iso> state=<in_progress|rate_limited|no_actionable|has_actionable|lookup_failed|no_walkthrough|unknown>
#   walkthrough-history        walkthrough の編集履歴をマーカー分類付きで列挙
#   coderabbit-trigger         '@coderabbit review' を投稿し comment ID と posted_at を出す
#   bot-reviews-since TS       TS 以降の bot review を列挙 (login/submitted/id)
#   codex-reaction             Codex の PR-issue リアクションを列挙 (eyes/+1/-1)
#   completion-summary         全 thread の resolved/hasMyReply + Codex リアクション + walkthrough 状態を出力
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
  # gh pr view の呼び出しを 1 回に集約 (number + commits[-1].committedDate)
  # TODO: LAST_PUSH_TS は commits[-1].committedDate を使用しており、実 push 時刻と乖離する場合がある。
  # gh API には PR commit ごとの pushedDate が無く、push 時刻の正確な取得には timeline events 走査が必要で複雑。
  # 現状は許容範囲として committedDate を採用。
  read -r n last_push <<< "$(gh pr view --json number,commits --jq '"\(.number) \(.commits[-1].committedDate)"')"
  if [ -z "$n" ] || [ -z "$last_push" ]; then
    echo "init: gh pr view failed (PR が見つからない、未認証、または PR check-out 外)" >&2
    return 1
  fi
  login=$(gh api user --jq .login)
  if [ -z "$login" ]; then
    echo "init: gh api user failed (未認証)" >&2
    return 1
  fi
  read -r owner repo <<< "$(gh repo view --json owner,name --jq '"\(.owner.login) \(.name)"')"
  if [ -z "$owner" ] || [ -z "$repo" ]; then
    echo "init: gh repo view failed" >&2
    return 1
  fi
  printf 'export OWNER=%q REPO=%q N=%q MY_LOGIN=%q LAST_PUSH_TS=%q\n' "$owner" "$repo" "$n" "$login" "$last_push"
}

# reviewThreads を cursor-based pagination で全件取得し、各 thread を JSON 行として出力
_fetch_all_review_threads() {
  owner_repo_n
  local cursor="null" has_next="true" json cursor_arg
  while [ "$has_next" = "true" ]; do
    if [ "$cursor" = "null" ]; then
      cursor_arg="null"
    else
      cursor_arg="\"$cursor\""
    fi
    json=$(gh api graphql -f query="query { repository(owner: \"$OWNER\", name: \"$REPO\") { pullRequest(number: $N) { reviewThreads(first: 100, after: $cursor_arg) { pageInfo { hasNextPage endCursor } nodes { id isResolved path line comments(first: 10) { nodes { databaseId author { login } body createdAt } } } } } } }")
    echo "$json" | jq -c '.data.repository.pullRequest.reviewThreads.nodes[]'
    has_next=$(echo "$json" | jq -r '.data.repository.pullRequest.reviewThreads.pageInfo.hasNextPage')
    cursor=$(echo "$json" | jq -r '.data.repository.pullRequest.reviewThreads.pageInfo.endCursor')
  done
}

cmd_unresolved_threads() {
  _fetch_all_review_threads | jq -c 'select(.isResolved == false)'
}

cmd_outside_diff_reviews() {
  owner_repo_n
  # 表記揺れ対応: "outside (the) diff range" / "outside the diff" / "outside-diff" 等を広く拾う
  gh api "repos/$OWNER/$REPO/pulls/$N/reviews" --paginate \
    --jq '.[] | select(.body != null and (.body | test("(?i)outside\\b.*diff"))) | {id: .id, user: (.user.login? // "ghost"), submitted: .submitted_at, body: .body}'
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
  # 複数回投稿された walkthrough の中で最新 (updated_at が最大) を返す
  gh api "repos/$OWNER/$REPO/issues/$N/comments" --paginate \
    --jq '[.[] | select(.user.login == "coderabbitai[bot]") | select(.body | startswith("<!-- This is an auto-generated comment: summarize by coderabbit.ai -->"))] | sort_by(.updated_at) | last | .id // empty'
}

cmd_walkthrough_state() {
  owner_repo_n
  local wid rc=0
  wid=$(cmd_walkthrough_id) || rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "updated_at=none state=lookup_failed"
    return
  fi
  if [ -z "$wid" ]; then
    echo "updated_at=none state=no_walkthrough"
    return
  fi
  gh api "repos/$OWNER/$REPO/issues/comments/$wid" --jq '
    .updated_at as $u
    | (.body // "") as $b
    | (if ($b | contains("review in progress by coderabbit.ai")) then "in_progress"
       elif ($b | contains("rate limited by coderabbit.ai")) then "rate_limited"
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
  if [ -z "$wid" ]; then
    echo "no walkthrough"
    return
  fi
  node_id=$(gh api "repos/$OWNER/$REPO/issues/comments/$wid" --jq '.node_id')
  gh api graphql -f query="query { node(id: \"$node_id\") { ... on IssueComment { userContentEdits(first: 100) { nodes { editedAt diff } } } } }" \
    --jq '.data.node.userContentEdits.nodes[] | {
      editedAt,
      in_progress: ((.diff // "") | contains("review in progress by coderabbit.ai")),
      rate_limited_marker: ((.diff // "") | contains("rate limited by coderabbit.ai")),
      has_actionable_phrase: ((.diff // "") | (contains("No actionable comments were generated") or test("Actionable comments posted: [0-9]+")))
    }'
}

cmd_coderabbit_trigger() {
  owner_repo_n
  # POST レスポンスの created_at を posted_at として返す (ローカル時計に依存しない)
  # 失敗時は jq に渡る前に exit code が非 0 になり (set -uo pipefail)、何も出力されない
  gh api "repos/$OWNER/$REPO/issues/$N/comments" -f body="@coderabbit review" \
    --jq '"comment_id=\(.id) posted_at=\(.created_at)"'
}

cmd_bot_reviews_since() {
  owner_repo_n
  local since="${1:?need timestamp ISO8601}"
  gh api "repos/$OWNER/$REPO/pulls/$N/reviews" --paginate \
    --jq ".[] | select(.user.login? // \"\" | endswith(\"[bot]\")) | select(.submitted_at > \"$since\") | \"\\(.user.login? // \"ghost\") submitted_at=\\(.submitted_at) id=\\(.id)\""
}

cmd_codex_reaction() {
  owner_repo_n
  gh api "repos/$OWNER/$REPO/issues/$N/reactions" \
    --jq '.[] | select(.user.login == "chatgpt-codex-connector[bot]") | "\(.content) at \(.created_at)"'
}

cmd_completion_summary() {
  owner_repo_n
  : "${MY_LOGIN:?MY_LOGIN not set; run 'review-resolve-status.sh init' first}"
  # 各セクションで「0 件」と「API 失敗」を区別する。bash 関数の終了ステータスは
  # `$?` で取れるが、コマンド置換 + パイプ後は失敗を捕捉しづらいため、各 helper を
  # `if cmd; then` で実行して取得成否を分岐する。
  echo "--- threads (resolved/unresolved + hasMyReply) ---"
  local threads
  if threads=$(_fetch_all_review_threads | jq -r --arg me "$MY_LOGIN" '
    "\(if .isResolved then "[resolved]  " else "[unresolved]" end) \(.path):\(.line) cid=\(.comments.nodes[0].databaseId? // "none") author=\(.comments.nodes[0].author.login? // "ghost") hasMyReply=\([.comments.nodes[].author.login?] | any(. == $me))"'); then
    echo "${threads:-(0件)}"
  else
    echo "(取得失敗)"
  fi
  echo "--- codex reactions ---"
  local reactions
  if reactions=$(cmd_codex_reaction); then
    echo "${reactions:-(0件)}"
  else
    echo "(取得失敗)"
  fi
  echo "--- coderabbit walkthrough state ---"
  local state
  if state=$(cmd_walkthrough_state); then
    echo "${state:-(0件)}"
  else
    echo "(取得失敗)"
  fi
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
      sed -n '5,30p' "$0"
      ;;
    *)
      echo "unknown subcommand: $sub" >&2
      exit 2
      ;;
  esac
}

main "$@"
