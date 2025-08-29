#!/bin/bash
# 複数のディレクトリ内にある全てのファイルを再帰的に検索し、
# 一つのディレクトリにシンボリックリンクをまとめて作成する。

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
)

# リンクを格納するディレクトリのフルパス
readonly DEST_DIR="${BASE_DIR}/${DEST_DIR_NAME}"

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
  find "${source_parent_dir}" -type f -print0 | while IFS= read -r -d $'\0' item_path; do
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
    echo "リンク作成: ${link_path} -> ${item_path}"
  done
done

echo "処理が完了しました。"
