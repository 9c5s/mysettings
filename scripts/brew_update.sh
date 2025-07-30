#!/bin/bash
# Homebrewのパッケージを更新、アップグレード、クリーンアップ、診断を実行する
brew update && brew upgrade && brew upgrade --cask --greedy && brew cleanup && brew doctor
