# レビュー指摘への対応

PR の未解決レビュースレッド全てに対し、対応方針 (採用/不採用) を決め、必要ならコード修正・push し、👍/👎 リアクションを付けて resolve する。スレッド外の指摘 (diff 範囲外コメント等) はコード修正と git log で完結させ PR 上で新規コメントを作らない。意思表示の手段が無いところにノイズを増やさないため。

定型操作は `scripts/review-resolve-status.sh` (以下 `rrs`) にまとめてある。jq クエリや GraphQL の引数を覚えず、サブコマンド名だけで呼べる。

## 初期化

`rrs init` が `OWNER`/`REPO`/`N`/`MY_LOGIN`/`LAST_PUSH_TS` を export 文として吐く。以降のサブコマンドはこの env を参照する。

```
# init が失敗 (auth/rate-limit/PR check-out 外) した場合に空 env で続行しないよう、
# 出力をいったん変数で受け取り init の exit code を eval 前にチェックする
_rrs_init_out=$(bash "$HOME/.claude/commands/scripts/review-resolve-status.sh" init) \
  && eval "$_rrs_init_out" \
  || { echo "rrs init failed; abort setup" >&2; return 1 2>/dev/null || exit 1; }
unset _rrs_init_out
alias rrs='bash "$HOME/.claude/commands/scripts/review-resolve-status.sh"'
```

以降の本文中の `rrs` は上記 alias を指す。alias を使わない場合は `bash "$HOME/.claude/commands/scripts/review-resolve-status.sh" <subcommand>` に読み替える。

## 手順 (通常モード)

1. `rrs unresolved-threads` で未解決スレッドを取得し、各スレッドの最初の comment 本文を読む
2. `rrs outside-diff-reviews` で「Outside diff range」を含む review 本文を取得。bot 表記揺れで漏れる場合は `gh api repos/$OWNER/$REPO/pulls/$N/reviews --paginate --jq '.[] | select(.body!="") | {id, user: .user.login, body}'` で全件目視併用
3. 各指摘について「採用/不採用」と理由を決める。コード修正が必要なら先に実装する
4. コード修正があれば `git add` → `git commit` → `git push` を実行する。通常モードはユーザーに push 確認、`--loop` モードは確認なしで即実行。push 後は commit hash を控え、`eval "$(bash "$HOME/.claude/commands/scripts/review-resolve-status.sh" init)"` を再実行して `LAST_PUSH_TS` を新 head に更新する
5. 各スレッドに対して: `rrs react <comment_id> +1` または `-1` でリアクション → `rrs resolve <thread_node_id>` で解決
6. 不採用で理由が分かりにくい場合のみ補足返信。`gh api repos/$OWNER/$REPO/pulls/$N/comments -f body="不採用 (理由1行)" -F in_reply_to=<comment_id>` 。リアクションだけで意思は伝わるので基本不要
7. diff 範囲外指摘への対応は commit にだけ残す。PR 上で issue comment やスレッド外コメントを作成しない
8. 完了確認: `rrs unresolved-threads | jq -s 'length'` が 0 になれば未解決スレッドは完了。diff 範囲外指摘は GitHub 上に完了マーカーが無いので、本コマンドの TaskList で対応有無を追跡する

## リアクションスタイル

- スレッドの最初の comment に 👍/👎 リアクションのみ。テキスト返信はしない。採用 commit hash は同 push の git log で辿れるので重複説明にならない
- 修正コミットのコード/docs コメントには設計判断の WHY だけ書く。「N 巡目指摘」「PR #X で指摘」のような経緯ラベルは git log と PR から参照できるので書かない
- **不採用時のみ coderabbit (coderabbitai[bot]) に対してだけ簡潔な理由を添えて返信する**。他の bot (gemini-code-assist, chatgpt-codex-connector など) は不採用でもリアクションのみで返信しない。理由返信は 1〜2 行・日本語・「だ・である」調

## --loop モード (`/review-resolve --loop`)

1 巡対応後も bot の追加レビューを監視し、来なくなるまで自動対応を繰り返す。通常モードとの違いは:

- 反復中の commit/push はユーザー確認なしで即実行 (起動時点で承認済みとみなす)
- bot 監視は `Monitor` ツール (パッシブ) で行い、`ScheduleWakeup` での能動 polling は使わない。polling は cache を焼くだけで効率が悪い

### bot の終了シグナル

各 bot は固有の「提案なし」シグナルを持つ。Monitor の通知だけでは判定できないものは能動確認する。

**Codex (`chatgpt-codex-connector[bot]`)**: PR issue へのリアクションで状態を示す:

| 内容 | 意味 |
|---|---|
| 👀 `eyes` | レビュー実行中 (push 後 5〜12 分継続) |
| 👍 `+1` | レビュー完了、提案事項なし |
| (なし) | 未着手 もしくは 完了して新規 review/comment を投稿済み |

`rrs codex-reaction` で確認。LAST_PUSH_TS より新しい `+1` があれば即終了して良い。

**CodeRabbit (`coderabbitai[bot]`)**: walkthrough コメント (PR 作成時に作る 1 件) を **edit して** レビュー結果を反映する。新規 issue comment は作らないため、Monitor の `created_at` 監視は通過する。

`rrs walkthrough-state` が `state=no_actionable` を返し、かつ `updated_at > LAST_PUSH_TS` なら「指摘なし」確定。`has_actionable` なら inline 指摘が reviewThread として現れているはずなので Monitor で捕捉される。詳細は後述の「CodeRabbit walkthrough の段階更新」参照。

**gemini-code-assist[bot]**: 観測されている終了シグナルが無い。無反応 = 提案なしとして時間 fallback で判定する。

### 終了条件

通常終了 (全 bot がクリーンを報告) は以下を **全て** 満たす場合に成立:

- Codex: `+1` リアクションが `LAST_PUSH_TS` より新しい (👀 が `+1` に切り替わっている)
- CodeRabbit: walkthrough `state=no_actionable` + `updated_at > LAST_PUSH_TS` + `rrs outside-diff-reviews "$LAST_PUSH_TS"` が空

片方の bot だけクリーン報告した時点で停止すると、もう片方の後続 findings (例: Codex 👍 後に CodeRabbit が actionable thread 投稿) を取りこぼすため OR ではなく AND で判定する。

Fallback 終了 (どれか 1 つ満たせば停止):

- 最終 push から 15 分以上、全 bot から新規 review/comment/thread・walkthrough 更新・codex リアクション変化・`poll-failed` も全て無い (= 真の無音)
- ユーザー指示 (「終了」「止めて」等)

### 監視 Monitor (起動 1 回・persistent)

`Monitor` ツールに以下を `persistent: true`, `timeout_ms: 3600000` で渡す。終了時 `TaskStop`。walkthrough は edit なので別途 updated_at を tail する:

```
# pipefail: rrs | jq の左側 (rrs) が失敗しても jq が 0 で抜けて poll-failed が出ないのを防ぐ
set -o pipefail

last="$LAST_PUSH_TS"
walkthrough_last=""
codex_reaction_last=""

# BSD (date -r EPOCH) と GNU (date -d @EPOCH) の両対応で 1 秒戻した ISO8601 を返す
date_minus_1s() {
  local epoch=$(($(date +%s) - 1))
  date -u -r "$epoch" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
    || date -u -d "@$epoch" +%Y-%m-%dT%H:%M:%SZ
}

while true; do
  # 次回 last の候補を polling 開始前 (= polling 完了より過去) に確定する。
  # polling 中に created された event は今回の last より新しく next_watermark より古くなり、
  # 今回のクエリで漏れた場合でも次回 iteration で必ず拾える。
  next_watermark=$(date_minus_1s)
  failed=0

  # 失敗時は stdout に "poll-failed: ..." を出して通知化する。失敗を黙殺すると
  # 15 分タイムアウト判定で「無音」と区別できず誤って終了するため。
  gh api --paginate "repos/$OWNER/$REPO/pulls/$N/reviews" \
    --jq ".[] | select(.submitted_at > \"$last\") | select(.user.login != \"$MY_LOGIN\") | \"review: \(.user.login) at \(.submitted_at) id=\(.id)\"" \
    || { echo "poll-failed: reviews"; failed=1; }
  gh api --paginate "repos/$OWNER/$REPO/issues/$N/comments" \
    --jq ".[] | select(.created_at > \"$last\") | select(.user.login != \"$MY_LOGIN\") | \"comment: \(.user.login) at \(.created_at) id=\(.id)\"" \
    || { echo "poll-failed: comments"; failed=1; }
  # rrs unresolved-threads は GraphQL pagination 済 (review-resolve-status.sh 側で cursor 追跡)
  bash "$HOME/.claude/commands/scripts/review-resolve-status.sh" unresolved-threads \
    | jq -r --arg last "$last" --arg me "$MY_LOGIN" \
      '.comments.nodes[] | select(.createdAt > $last) | select(.author.login != $me) | "thread: \(.author.login) at \(.createdAt) cid=\(.databaseId)"' \
    || { echo "poll-failed: threads"; failed=1; }
  if walkthrough_now=$(bash "$HOME/.claude/commands/scripts/review-resolve-status.sh" walkthrough-state); then
    if [ "$walkthrough_now" != "$walkthrough_last" ] && [ -n "$walkthrough_last" ]; then
      echo "walkthrough: $walkthrough_now"
    fi
    walkthrough_last="$walkthrough_now"
  else
    # cmd_walkthrough_state は lookup_failed のとき exit 1 を返す。no_walkthrough は exit 0
    echo "poll-failed: walkthrough-state"
    failed=1
  fi
  # Codex の eyes/+1 リアクション変化を通知。Codex が新 review を出さず +1 だけ付けた
  # 「クリーン完了」も検知できるようにする
  if codex_reaction_now=$(bash "$HOME/.claude/commands/scripts/review-resolve-status.sh" codex-reaction); then
    codex_reaction_now=$(printf '%s' "$codex_reaction_now" | sort -u | tr '\n' '|')
    if [ "$codex_reaction_now" != "$codex_reaction_last" ] && [ -n "$codex_reaction_last" ]; then
      echo "codex-reaction: $codex_reaction_now"
    fi
    codex_reaction_last="$codex_reaction_now"
  else
    echo "poll-failed: codex-reaction"
    failed=1
  fi

  # polling が 1 つでも失敗していたら watermark を進めない (失敗中に created された event を
  # 次回でも拾える状態に保つ)。全 polling 成功時のみ watermark を更新する
  if [ "$failed" -eq 0 ]; then
    last="$next_watermark"
  fi
  sleep 30
done
```

### ループ手順

1. 通常手順 1〜8 を実行 (1 巡目)
2. push 後 `Monitor` を上記コマンドで起動
3. notification 受信時:
   - a. 内容確認 → 対応方針決定
   - b. 大規模変更 (※後述) はユーザー確認 → 承認後実装
   - c. 修正 → `bun plugin/src/patch-server.ts --make` 等の再生成 → テスト → `git add` → `git commit` → `git push` (確認なし) → `eval "$(rrs init)"` を再実行して `LAST_PUSH_TS` を新 head に更新
   - d. `rrs react <cid> +1|-1` + `rrs resolve <node_id>`
   - e. `rrs codex-reaction` で 👍 なら Codex 観点はクリア (即終了はせず CodeRabbit の終了条件 (f) と AND で判定)、👀 なら Codex は in_progress として待機継続
   - f. `rrs walkthrough-state` が `no_actionable` で `updated_at > LAST_PUSH_TS` **かつ** `rrs outside-diff-reviews "$LAST_PUSH_TS"` も空なら CodeRabbit 観点で終了確定。`no_actionable` は inline 指摘数 0 を意味するだけで、outside-diff/nitpick が body に残っているケースを取りこぼすため両方をチェックする。`outside-diff-reviews` には現 push 以降の cutoff を渡し、過去 push で既に対応済の outside-diff が残って永久に false にならないようにする
4. 15 分新着もリアクション変化も walkthrough 更新も `poll-failed` も無ければ終了判定。Codex 👀 が残っていれば +5〜10 分延長。`poll-failed: ...` が連続して出ている間は API 不調なので終了判定の無音タイマーをリセットする
5. 終了確定で `TaskStop` → ユーザーに完了報告

### 大規模変更の合図

同じ箇所への指摘が連続し、対策を重ねるたびに別の穴が露呈する場合は、対症療法ではなく根本設計の見直しをユーザーに提案する。レース対策・ガード・遅延の各論を積み重ねると複雑度だけが増え新しい問題を呼ぶ傾向がある。

## CodeRabbit walkthrough の段階更新

walkthrough コメントは段階的に edit され、edit ごとに状態マーカーが切り替わる:

| マーカー (HTML コメント) | 意味 | 出現タイミング |
|---|---|---|
| `<!-- ...: review in progress by coderabbit.ai -->` | 進行中 (`> [!NOTE] Currently processing...`) | 0th (~15s)、1st (~1.5m) |
| `<!-- ...: rate limited by coderabbit.ai -->` | レートリミット (`> [!WARNING] Review limit reached`) | rate-limit 発火時 (~8m) |
| `No actionable comments were generated in the recent review. 🎉` | 完了・指摘なし | 完了 edit (~5〜8m) |
| `Actionable comments posted: N` (N > 0) | 完了・inline 指摘あり | 完了 edit (~5〜8m) |

判定で踏まないと混乱する点:

- **進行中マーカーが残っている間は完了とみなさない**。1.5 分時点で Walkthrough/Changes/Pre-merge checks が body に表示されていても、進行中マーカーが消えるまでは 5〜8 分待つ
- **過去のレートリミット履歴は body に残り続ける**。`rate limited` マーカーの単純存在チェックは過去の rate-limit セッションでも true になる。`rrs walkthrough-state` は最新 edit の状態だけを見るので安全
- **`@coderabbit review` への自動応答** (Review triggered, 投稿の数秒後): incremental review system のため既にレビュー済みコミットは re-review されない可能性がある旨の注記付き。新規 commit 無しで再依頼してもレビュー結果が変わらないことがある

walkthrough の編集履歴を直接見たい場合は `rrs walkthrough-history` (各 edit を 3 マーカーで分類した JSON 行)。

## 補足コマンド

- `rrs coderabbit-trigger` : `@coderabbit review` 投稿+時刻記録 (1 行で済む)
- `rrs bot-reviews-since <ts>` : 指定時刻以降の bot review 一覧
- `rrs completion-summary` : 未解決スレッド数 + Codex リアクション + walkthrough 状態を 1 ブロックで出力 (最終確認用)

`minimizeComment` は表示の非表示化であり resolve ではない。resolve には必ず `rrs resolve` (= `resolveReviewThread` mutation) を使う。

