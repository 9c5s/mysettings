# レビュー指摘への対応

各指摘への対応方針が既に決まっているPRの未解決レビュースレッド全てに返信し、解決済みにしてプッシュする

## 前提条件

- 各指摘への対応(修正する/しないとその理由)が既に決まっていること

## 手順

1. 現在のブランチのPR番号を特定する
2. 修正が必要な指摘で未実装のものがあれば、先にコード修正を行う
3. [/push](push.md) でコミットとプッシュを行う。修正がなければプッシュのみ行う。**プッシュ前に必ずユーザーに確認を取ること**
4. 未解決のレビュースレッドを全て取得する
5. 各スレッドに対して:
   - 対応内容と理由を日本語でスレッド返信する
   - bot(coderabbitai, gemini-code-assistなど)への返信は「だ・である」調で簡潔にする
   - スレッドを解決済みにする
6. **完了確認**: 全スレッドが以下の両方を満たすことを検証する
   - `isResolved == true` (解決済み)
   - 最後のコメントが自分のアカウント (返信済み)
   - 未達のスレッドがあれば手順5に戻る

## 使用するコマンド

### レビュースレッド取得

```
gh api graphql -f query='query { repository(owner: "{owner}", name: "{repo}") { pullRequest(number: {N}) { reviewThreads(first: 50) { nodes { id isResolved comments(first: 1) { nodes { body author { login } databaseId } } } } } } }'
```

### スレッド返信

```
gh api repos/{owner}/{repo}/pulls/{N}/comments -f body="返信内容" -F in_reply_to={comment_id}
```

### スレッド解決

```
gh api graphql -f query='mutation { resolveReviewThread(input: { threadId: "{thread_node_id}" }) { thread { isResolved } } }'
```

### 完了確認

```
gh api graphql -f query='query { repository(owner: "{owner}", name: "{repo}") { pullRequest(number: {N}) { reviewThreads(first: 50) { nodes { id isResolved comments(last: 1) { nodes { author { login } } } } } } } }'
```

各スレッドで `isResolved == true` かつ最終コメントが自分のアカウントであることを確認する。

注意: `minimizeComment`はコメントの非表示であり、スレッドの解決ではない
