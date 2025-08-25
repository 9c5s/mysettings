<#
.SYNOPSIS
    .DS_Store および ._.DS_Store ファイルを検索し削除する。

.DESCRIPTION
    指定されたドライブを再帰的に検索し、.DS_Store および ._.DS_Store ファイルを削除する。
    -Includes パラメータで検索対象のドライブを、-Excludes パラメータで除外するドライブを指定できる。

.PARAMETER Includes
    検索対象とするドライブの配列。エイリアスは-I
    例: 'C', 'D:', 'cde'

.PARAMETER Excludes
    検索から除外するドライブの配列。エイリアスは-E
    例: 'Y', 'Z:', 'yz'

.EXAMPLE
    # CドライブとDドライブのみを検索
    .\dsstore_erase.ps1 -Includes C, D

.EXAMPLE
    # CドライブとDドライブのみを検索（エイリアス使用）
    .\dsstore_erase.ps1 -I C, D

.EXAMPLE
    # C, D, Eドライブを検索（連結表記、大文字小文字混合）
    .\dsstore_erase.ps1 -I cDe

.EXAMPLE
    # Yドライブを除外してすべてのドライブを検索
    .\dsstore_erase.ps1 -Excludes Y

.EXAMPLE
    # Yドライブを除外してすべてのドライブを検索（エイリアス使用）
    .\dsstore_erase.ps1 -E Y

.EXAMPLE
    # すべてのローカルディスクとネットワークドライブを検索
    .\dsstore_erase.ps1
#>
param (
    # 検索対象のドライブを指定
    [Alias('I')]
    [string[]]$Includes,

    # 検索から除外するドライブを指定
    [Alias('E')]
    [string[]]$Excludes
)

# 削除ファイル数のカウンター
$deletedFilesCount = 0

Write-Host ".DS_Store ファイルのクリーンアップ処理を開始します。"
Write-Host "--------------------------------------------------"

# ドライブレターを正規化する関数
function Convert-DriveLetters {
    param([string[]]$DriveInputs)

    if (-not $DriveInputs) { return @() }

    return $DriveInputs | ForEach-Object {
        $item = $_.TrimEnd(':')
        if ($item.Length -gt 1) {
            # "cde" のような連結文字列を個別のドライブレターに分割
            $item.ToCharArray() | ForEach-Object { "$($_.ToString().ToUpper()):" }
        }
        else {
            # "c" や "C" のような単一の文字
            "$($item.ToUpper()):"
        }
    }
}

# 引数のドライブレターを正規化
$normalizedIncludes = Convert-DriveLetters -DriveInputs $Includes
$normalizedExcludes = Convert-DriveLetters -DriveInputs $Excludes

# 探査対象ドライブのリストを決定
$drivesToScan = if ($normalizedIncludes) {
    # Includesが指定されていれば、そのドライブ情報を取得
    Get-CimInstance -ClassName Win32_LogicalDisk | Where-Object { $_.DeviceID -in $normalizedIncludes }
}
else {
    # Includesが指定されていなければ、ローカルディスク(3)とネットワークドライブ(4)を取得
    Get-CimInstance -ClassName Win32_LogicalDisk | Where-Object { $_.DriveType -in 3, 4 }
}

# 除外ドライブが指定されていれば、リストから除外
if ($normalizedExcludes.Count -gt 0) {
    $drivesToScan = $drivesToScan | Where-Object { $_.DeviceID -notin $normalizedExcludes }
}

# ドライブをループして処理
$drivesToScan | ForEach-Object {
    $drivePath = $_.DeviceID + "\"

    # ドライブパスの存在をテスト
    if (Test-Path -Path $drivePath) {
        Write-Host "ドライブを検索中: $drivePath"

        # .DS_Store ファイルと ._.DS_Store ファイルを再帰的に検索
        $filesToDelete = Get-ChildItem -Path $drivePath -Include ".DS_Store", "._.DS_Store" -Recurse -Force -ErrorAction SilentlyContinue

        # 見つかったファイルを削除
        foreach ($file in $filesToDelete) {
            try {
                Remove-Item -Path $file.FullName -Force -ErrorAction Stop
                Write-Host "  削除しました: $($file.FullName)"
                $deletedFilesCount++
            }
            catch {
                Write-Host "  エラー: $($file.FullName) の削除中にエラーが発生しました - $($_.Exception.Message)"
            }
        }
    }
    else {
        Write-Host "ドライブが見つかりません。スキップします: $drivePath"
    }
}

Write-Host "--------------------------------------------------"
Write-Host "クリーンアップ処理が完了しました。"
Write-Host "合計 $deletedFilesCount 個のファイルを削除しました。"
