# リモートとの完全同期

## 基本的な同期処理

git fetch --all
git reset --hard origin/main
git clean -fd
git remote prune origin

## マージ済みブランチの安全な削除

git branch --merged | grep -v -E "^\*|main$" | xargs -r git branch -d 2>/dev/null || true

## 最終同期

git checkout main
git pull origin main
