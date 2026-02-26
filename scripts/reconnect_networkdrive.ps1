#
# ネットワークドライブを切断して再接続するスクリプト
#

# --- ユーザー入力 ---
# ドライブレターの入力を求める
$driveName = Read-Host "再接続するドライブレターを入力してください (例:Z)"
# ネットワークパスの入力を求める
$networkPath = Read-Host "再接続するネットワークパスを入力してください (例:\\server\share)"

# --- 入力値の検証 ---
# 入力がアルファベット一文字であるか正規表現でチェック
if (-not ($driveName -match '^[a-zA-Z]$')) {
    Write-Error "無効なドライブレターです"
    # スクリプトの実行を停止
    return
}
# "Z" のような入力から "Z:" の形式に変換
$driveLetter = "$($driveName):"

# 入力されたパスがUNC形式（\\で始まる）かを確認
if (-not ($networkPath.StartsWith("\\"))) {
    Write-Warning "ネットワークパスは通常'\\'で始まります 入力内容を確認してください"
}
# パスが空でないかチェック
if ([string]::IsNullOrWhiteSpace($networkPath)) {
    Write-Error "ネットワークパスが空です"
    return
}

# --- 切断処理 ---
Write-Host "`n$driveLetter の切断を試みます"
try {
    # PowerShellドライブとして存在すれば削除
    if (Get-PSDrive $driveName -ErrorAction SilentlyContinue) {
        Remove-PSDrive -Name $driveName -Force -ErrorAction SilentlyContinue
    }
    # COMオブジェクトを使い、OSレベルでの永続的なマッピングを削除
    $network = New-Object -ComObject WScript.Network
    $network.RemoveNetworkDrive($driveLetter, $true, $true)
    Write-Host "$driveLetter を切断しました"
}
catch {
    # ドライブが存在しない場合など、切断に失敗しても処理を続ける
    Write-Host "$driveLetter は接続されていなかったか、切断できませんでした"
}

# --- 再接続処理 ---
Write-Host "`n$driveLetter を $networkPath に再接続します"
try {
    # 永続的なドライブとして再接続 (-Persist)
    # エラーが発生した場合はスクリプトを停止 (-ErrorAction Stop)
    New-PSDrive -Name $driveName -PSProvider "FileSystem" -Root $networkPath -Persist -ErrorAction Stop
    Write-Host "$driveLetter の再接続に成功しました"
}
catch {
    # エラーが発生した場合、その詳細を出力
    Write-Error "再接続に失敗しました エラー: $($_.Exception.Message)"
}
