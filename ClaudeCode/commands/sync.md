# リモートとの完全同期

以下のスクリプトをそのまま実行する。

```bash
set -euo pipefail

# メインブランチの検出
main_branch=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@') || {
  git remote set-head origin --auto
  main_branch=$(git symbolic-ref refs/remotes/origin/HEAD | sed 's@^refs/remotes/origin/@@')
}
echo "Main branch: $main_branch"

# メインブランチの pull
git checkout "$main_branch"
git pull origin "$main_branch"

# リモート追跡ブランチの整理
git remote prune origin

# マージ済みローカルブランチの削除
for branch in $(git branch --format='%(refname:short)' | grep -v "^${main_branch}$"); do
  if [ -z "$(git cherry "$main_branch" "$branch" 2>/dev/null | grep '^\+')" ]; then
    git branch -D "$branch"
  else
    echo "Skipped: $branch (has unmerged commits)"
  fi
done
```
