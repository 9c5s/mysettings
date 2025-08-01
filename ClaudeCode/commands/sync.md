# リモートとの完全同期

git fetch --all && git reset --hard origin/main && git clean -fd && git remote prune origin && git branch -d $(git branch --merged | grep -v '\*\|main\|main' | tr -d ' ') && git checkout main && git pull origin main
