#!/bin/bash
# Brewfile バックアップとソートスクリプト

readonly BREWFILE="${HOME}/projects/mysettings/mac/Homebrew/Brewfile"

# Brewfileの生成
brew bundle dump --no-vscode --force --file "${BREWFILE}"

# 各セクション用の配列を初期化
declare -a taps=()
declare -a brews=()
declare -a casks=()
declare -a mas_apps=()

# Brewfileを読み込んでセクションごとに分類
while IFS= read -r line; do
  if [[ ${line} =~ ^tap ]]; then
    taps+=("${line}")
  elif [[ ${line} =~ ^brew ]]; then
    brews+=("${line}")
  elif [[ ${line} =~ ^cask ]]; then
    casks+=("${line}")
  elif [[ ${line} =~ ^mas ]]; then
    mas_apps+=("${line}")
  fi
done < "${BREWFILE}"

# ソートされた内容をファイルに書き戻す
{
  # 各セクションをソートして出力
  if [[ ${#taps[@]} -gt 0 ]]; then
    printf '%s\n' "${taps[@]}" | sort
  fi
  if [[ ${#brews[@]} -gt 0 ]]; then
    printf '%s\n' "${brews[@]}" | sort
  fi
  if [[ ${#casks[@]} -gt 0 ]]; then
    printf '%s\n' "${casks[@]}" | sort
  fi
  if [[ ${#mas_apps[@]} -gt 0 ]]; then
    printf '%s\n' "${mas_apps[@]}" | sort
  fi
} > "${BREWFILE}"

echo "Brewfileが更新されました: ${BREWFILE}"
