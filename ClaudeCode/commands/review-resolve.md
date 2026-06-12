# レビュー指摘への対応

各指摘への対応方針が既に決まっているPRの未解決レビュースレッド全てに返信し、解決済みにしてプッシュする

## 前提条件

- 各指摘への対応(修正する/しないとその理由)が既に決まっていること

## 手順

1. 現在のブランチのPR番号を特定する
2. 未解決のレビュースレッドを全て取得する
3. **diff範囲外コメントも取得する**: レビュー本文のみに埋まる指摘(CodeRabbitの「Outside diff range comments」等)はreviewThreadsに現れない。全レビューのbodyを取得し、未対応の指摘が無いか必ず確認する
4. 修正が必要な指摘で未実装のものがあれば、先にコード修正を行う
5. [/push](push.md) でコミットとプッシュを行う。修正がなければプッシュのみ行う。**プッシュ前に必ずユーザーに確認を取ること**
6. 各スレッドに対して:
   - 対応内容と理由を日本語でスレッド返信する
   - bot(coderabbitai, gemini-code-assistなど)への返信は「だ・である」調で簡潔にする
   - スレッドを解決済みにする
7. diff範囲外コメントに対応した場合: スレッド解決の対象外のため、該当レビューへのpermalinkを引用したPR会話コメントで対応内容を記す
8. **完了確認**: 全スレッドが以下の両方を満たすことを検証する
   - `isResolved == true` (解決済み)
   - 自分のアカウントの返信が含まれる (botが自動返信するため最終コメントでは判定不可)
   - 未達のスレッドがあれば手順6に戻る
   - diff範囲外コメントは対応コメントの投稿をもって完了とする

## 使用するコマンド

### レビュースレッド取得

```
gh api graphql -f query='query { repository(owner: "{owner}", name: "{repo}") { pullRequest(number: {N}) { reviewThreads(first: 50) { nodes { id isResolved comments(first: 1) { nodes { body author { login } databaseId } } } } } } }'
```

### diff範囲外コメントの取得(レビュー本文の走査)

```
gh api repos/{owner}/{repo}/pulls/{N}/reviews --paginate --jq '.[] | select(.body != null and .body != "") | {id: .id, user: .user.login, submitted: .submitted_at, body: .body}'
```

「Outside diff range」「outside the diff」等の見出しや、ファイルパス+行番号付きの指摘が本文に含まれていないか確認する。

### diff範囲外コメントへの対応コメント投稿(スレッド解決の代替)

```
gh api repos/{owner}/{repo}/issues/{N}/comments -f body="対応内容(該当レビューのpermalink https://github.com/{owner}/{repo}/pull/{N}#pullrequestreview-{review_id} を引用)"
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
gh api graphql -f query='query { repository(owner: "{owner}", name: "{repo}") { pullRequest(number: {N}) { reviewThreads(first: 50) { nodes { id isResolved comments(first: 10) { nodes { author { login } } } } } } } }' --jq '.data.repository.pullRequest.reviewThreads.nodes[] | {id: .id, resolved: .isResolved, hasMyReply: ([.comments.nodes[].author.login] | any(. == "{my_login}"))}'
```

各スレッドで `resolved == true` かつ `hasMyReply == true` であることを確認する。
botが自動返信するため `comments(last: 1)` ではなく全コメントから自分のアカウントを検索する。

注意: `minimizeComment`はコメントの非表示であり、スレッドの解決ではない
