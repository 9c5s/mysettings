#!/bin/bash
# 複数のディレクトリ内にある全てのファイルを再帰的に検索し、
# 一つのディレクトリにシンボリックリンクをまとめて作成する。

# コマンドライン引数の処理
CLEAN_MODE=false
if [[ "$1" == "--clean" ]] || [[ "$1" == "-c" ]]; then
  CLEAN_MODE=true
fi

# リンク元とリンク先を配置する親ディレクトリ
readonly BASE_DIR="/Volumes/xin_VJ/VJ/アイマス"

# リンクをまとめるディレクトリ名
readonly DEST_DIR_NAME="総合"

# 中身をリンクする対象のディレクトリ名のリスト
readonly SOURCE_DIRS=(
  "_etc"
  "AS"
  "CG"
  "GM"
  "ML"
  "SC"
  "SM"
  "VL"
  "複合"
  "tmp"
)

# リンクを格納するディレクトリのフルパス
readonly DEST_DIR="${BASE_DIR}/${DEST_DIR_NAME}"

# クリーンモードの処理
if [ "${CLEAN_MODE}" = true ]; then
  if [ -d "${DEST_DIR}" ]; then
    echo "既存のシンボリックリンクを削除しています..."
    find "${DEST_DIR}" -type l -delete
    echo "シンボリックリンクの削除が完了しました。"
    echo ""
  else
    echo "対象ディレクトリが存在しません: ${DEST_DIR}"
    echo "新規作成して続行します。"
    echo ""
  fi
fi

# リンク格納用ディレクトリの作成（存在しない場合）
if ! [ -d "${DEST_DIR}" ]; then
  # ディレクトリ作成
  mkdir -p "${DEST_DIR}"
  echo "ディレクトリを作成しました: ${DEST_DIR}"
fi

# 各ディレクトリを再帰的に走査
for dir in "${SOURCE_DIRS[@]}"; do
  source_parent_dir="${BASE_DIR}/${dir}"

  # リンク元ディレクトリの存在を確認
  if [ ! -d "${source_parent_dir}" ]; then
    echo "警告: ディレクトリが見つかりません。スキップします: ${source_parent_dir}"
    continue
  fi

  # findでファイルを再帰的に検索し、見つかったファイルに対してリンクを作成
  # ファイル名に特殊文字が含まれていても安全に処理するため、-print0とread -dを使用
  # ._で始まるmacOSのメタデータファイルは除外
  find "${source_parent_dir}" -type f ! -name "._*" -print0 | while IFS= read -r -d $'\0' item_path; do
    item_name=$(basename "${item_path}")
    link_path="${DEST_DIR}/${item_name}"

    # リンク先に同名のファイルやリンクが既に存在するかチェック
    # -L はシンボリックリンクそのものの存在を確認する
    if [ -e "${link_path}" ] || [ -L "${link_path}" ]; then
      echo "既に存在するためスキップします: ${link_path}"
      continue
    fi

    # シンボリックリンクを作成
    ln -s "${item_path}" "${link_path}"
    echo "リンク作成: ${item_path} -> ${link_path}"
  done
done

echo "処理が完了しました。"
