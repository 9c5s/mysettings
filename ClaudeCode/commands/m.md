# リモートとの完全同期

git fetch --all && git reset --hard origin/master && git clean -fd && git remote prune origin && git branch -d $(git branch --merged | grep -v '\*\|master\|main' | tr -d ' ') && git checkout master && git pull origin master
