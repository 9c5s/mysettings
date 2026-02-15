<#
.SYNOPSIS
    システムとユーザーのPATH環境変数を診断・修正する。

.DESCRIPTION
    以下の問題を検出し修正する:
    - 存在しないディレクトリの削除
    - 重複エントリの排除
    - System PATHに紛れ込んだユーザー固有パスをUser PATHへ移動
    - 切り詰められた不正なパスの削除 (ユーザーに確認)
    - アルファベット順にソート

    診断結果を表示した後、ユーザーに適用するか確認する。

.EXAMPLE
    .\fix_path_env.ps1
#>

Set-StrictMode -Version Latest

# 管理者権限チェックと自動昇格
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "管理者権限が必要です。昇格して再実行します..." -ForegroundColor Yellow
    Start-Process pwsh.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

# --- ユーティリティ ---

function Write-Status {
    param([string]$Message, [string]$Color = "White")
    Write-Host $Message -ForegroundColor $Color
}

function Write-Fix {
    param([string]$Message)
    Write-Host "  [+] $Message" -ForegroundColor Green
}

function Write-Remove {
    param([string]$Message)
    Write-Host "  [-] $Message" -ForegroundColor Red
}

function Write-Move {
    param([string]$Message)
    Write-Host "  [>] $Message" -ForegroundColor Cyan
}

# パスを正規化する (末尾のバックスラッシュを除去し小文字化)
function Get-NormalizedPath {
    param([string]$Path)
    return $Path.Trim().TrimEnd('\').ToLower()
}

# パスがユーザー固有かどうか判定する
function Test-UserSpecificPath {
    param([string]$Path)
    $userProfile = $env:USERPROFILE.ToLower()
    $normalized = $Path.Trim().ToLower()
    return $normalized.StartsWith($userProfile) -or $normalized -match '^c:\\users\\'
}

# パスが明らかに切り詰められているか判定する
function Test-TruncatedPath {
    param([string]$Path)
    $trimmed = $Path.Trim()
    # 短すぎるパスで、既知のルートでない
    if ($trimmed.Length -lt 10 -and $trimmed -notmatch '^[A-Z]:\\Windows$') {
        return $true
    }
    # ディレクトリ名が1文字で終わる疑わしいパス
    $leaf = Split-Path $trimmed -Leaf -ErrorAction SilentlyContinue
    if ($leaf -and $leaf.Length -eq 1 -and $leaf -match '^[A-Za-z]$') {
        return $true
    }
    return $false
}

# 切り詰めが疑われるパスについてユーザーに確認する
# 戻り値: $true = 削除する, $false = 残す
function Confirm-TruncatedPath {
    param([string]$Path, [string]$Scope)
    Write-Host "  [!] 切り詰めの疑いがあります ($Scope): $Path" -ForegroundColor Yellow
    while ($true) {
        $response = Read-Host "    このパスを削除しますか? (y: 削除 / n: 残す)"
        switch ($response.ToLower()) {
            'y' { return $true }
            'n' { return $false }
            default { Write-Host "    y または n で回答してください。" -ForegroundColor Gray }
        }
    }
}

# y/n でユーザーに確認する
# 戻り値: $true = はい, $false = いいえ
function Confirm-YesNo {
    param([string]$Prompt)
    while ($true) {
        $response = Read-Host $Prompt
        switch ($response.ToLower()) {
            'y' { return $true }
            'n' { return $false }
            default { Write-Host "y または n で回答してください。" -ForegroundColor Gray }
        }
    }
}

# パスのリストをアルファベット順にソートする
function Get-SortedPathEntries {
    param([System.Collections.Generic.List[string]]$Entries)
    $sorted = [System.Collections.Generic.List[string]]::new(
        [string[]]($Entries | Sort-Object { (Get-NormalizedPath $_) })
    )
    return $sorted
}

# --- メイン処理 ---

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  PATH 環境変数 診断・修正ツール" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 現在のPATHを取得
$sysPathRaw = [Environment]::GetEnvironmentVariable('Path', 'Machine')
$usrPathRaw = [Environment]::GetEnvironmentVariable('Path', 'User')

$sysEntries = ($sysPathRaw -split ';') | Where-Object { $_ -and $_.Trim() } | ForEach-Object { $_.Trim() }
$usrEntries = ($usrPathRaw -split ';') | Where-Object { $_ -and $_.Trim() } | ForEach-Object { $_.Trim() }

Write-Status "--- 現在の状態 ---" "Cyan"
Write-Host "  System PATH: $($sysEntries.Count) エントリ ($($sysPathRaw.Length) 文字)"
Write-Host "  User PATH:   $($usrEntries.Count) エントリ ($($usrPathRaw.Length) 文字)"
Write-Host "  合計:        $($sysEntries.Count + $usrEntries.Count) エントリ ($($sysPathRaw.Length + $usrPathRaw.Length) 文字)"
Write-Host ""

# 問題カウンタ
$issueCount = 0

# 修正後のリスト
$newSysEntries = [System.Collections.Generic.List[string]]::new()
$newUsrEntries = [System.Collections.Generic.List[string]]::new()
# System PATHからUser PATHへ移動するエントリ
$movedToUser = [System.Collections.Generic.List[string]]::new()

# 重複チェック用のセット
$seenSys = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
$seenUsr = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)

# ============================
# System PATH の処理
# ============================
Write-Status "--- System PATH の診断 ---" "Cyan"

foreach ($entry in $sysEntries) {
    $normalized = Get-NormalizedPath $entry

    # 切り詰められたパスの検出
    if (Test-TruncatedPath $entry) {
        if (Confirm-TruncatedPath $entry "System") {
            Write-Remove "切り詰められたパス: $entry"
            $issueCount++
            continue
        } else {
            Write-Fix "保持します: $entry"
        }
    }

    # 重複の検出
    if (-not $seenSys.Add($normalized)) {
        Write-Remove "重複 (System内): $entry"
        $issueCount++
        continue
    }

    # ユーザー固有パスの検出 -> User PATHへ移動
    if (Test-UserSpecificPath $entry) {
        Write-Move "ユーザー固有パスをUser PATHへ移動します: $entry"
        $movedToUser.Add($entry)
        $issueCount++
        continue
    }

    # 存在しないパスの検出
    if (-not (Test-Path $entry)) {
        Write-Remove "存在しないパス: $entry"
        $issueCount++
        continue
    }

    $newSysEntries.Add($entry)
}

Write-Host ""

# ============================
# User PATH の処理
# ============================
Write-Status "--- User PATH の診断 ---" "Cyan"

# まずUser PATHの既存エントリを処理
foreach ($entry in $usrEntries) {
    $normalized = Get-NormalizedPath $entry

    # 切り詰められたパスの検出
    if (Test-TruncatedPath $entry) {
        if (Confirm-TruncatedPath $entry "User") {
            Write-Remove "切り詰められたパス: $entry"
            $issueCount++
            continue
        } else {
            Write-Fix "保持します: $entry"
        }
    }

    # 重複の検出
    if (-not $seenUsr.Add($normalized)) {
        Write-Remove "重複 (User内): $entry"
        $issueCount++
        continue
    }

    # 存在しないパスの検出
    if (-not (Test-Path $entry)) {
        Write-Remove "存在しないパス: $entry"
        $issueCount++
        continue
    }

    $newUsrEntries.Add($entry)
}

# Systemから移動されたエントリを追加 (重複しなければ)
foreach ($entry in $movedToUser) {
    $normalized = Get-NormalizedPath $entry
    if ($seenUsr.Add($normalized)) {
        # 存在するパスのみ移動 (存在しなければ削除扱い)
        if (Test-Path $entry) {
            Write-Fix "User PATHに追加します: $entry"
            $newUsrEntries.Add($entry)
        } else {
            Write-Remove "移動元が存在しないため削除します: $entry"
        }
    } else {
        Write-Remove "User PATHに既に存在するため削除します: $entry"
    }
}

Write-Host ""

# ============================
# ソート
# ============================
$newSysEntries = Get-SortedPathEntries $newSysEntries
$newUsrEntries = Get-SortedPathEntries $newUsrEntries

# ============================
# 結果サマリー
# ============================
Write-Status "--- 結果サマリー ---" "Cyan"
Write-Host "  検出された問題: $issueCount 件"
Write-Host ""
Write-Host "  System PATH: $($sysEntries.Count) -> $($newSysEntries.Count) エントリ"
Write-Host "  User PATH:   $($usrEntries.Count) -> $($newUsrEntries.Count) エントリ"

$newSysPathStr = $newSysEntries -join ';'
$newUsrPathStr = $newUsrEntries -join ';'
$totalLen = $newSysPathStr.Length + $newUsrPathStr.Length
Write-Host "  合計文字数:  $($sysPathRaw.Length + $usrPathRaw.Length) -> $totalLen 文字"
Write-Host ""

Write-Status "--- 修正後の System PATH ---" "Cyan"
foreach ($e in $newSysEntries) { Write-Host "  $e" }
Write-Host ""
Write-Status "--- 修正後の User PATH ---" "Cyan"
foreach ($e in $newUsrEntries) { Write-Host "  $e" }
Write-Host ""

if ($issueCount -eq 0) {
    Write-Status "問題は検出されませんでした。修正は不要です。" "Green"
    Read-Host "終了するには Enter キーを押してください"
    exit 0
}

# ============================
# ユーザーに適用確認
# ============================
if (-not (Confirm-YesNo "この内容で変更を適用しますか? (y/n)")) {
    Write-Status "変更は適用されませんでした。" "Yellow"
    Read-Host "終了するには Enter キーを押してください"
    exit 0
}

# ============================
# バックアップの作成
# ============================
$backupDir = Join-Path $env:USERPROFILE ".path_backup"
if (-not (Test-Path $backupDir)) {
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
}
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$sysPathRaw | Out-File (Join-Path $backupDir "system_path_$timestamp.txt") -Encoding UTF8
$usrPathRaw | Out-File (Join-Path $backupDir "user_path_$timestamp.txt") -Encoding UTF8
Write-Status "バックアップを作成しました: $backupDir" "Green"
Write-Host ""

# ============================
# 変更の適用
# ============================
Write-Status "変更を適用しています..." "Yellow"

try {
    [Environment]::SetEnvironmentVariable('Path', $newSysPathStr, 'Machine')
    Write-Fix "System PATHを更新しました"
} catch {
    Write-Host "  [ERROR] System PATHの更新に失敗しました: $_" -ForegroundColor Red
    Read-Host "終了するには Enter キーを押してください"
    exit 1
}

try {
    [Environment]::SetEnvironmentVariable('Path', $newUsrPathStr, 'User')
    Write-Fix "User PATHを更新しました"
} catch {
    Write-Host "  [ERROR] User PATHの更新に失敗しました: $_" -ForegroundColor Red
    Read-Host "終了するには Enter キーを押してください"
    exit 1
}

Write-Host ""
Write-Status "全ての変更を適用しました。新しいターミナルを開いて反映を確認してください。" "Green"
Read-Host "終了するには Enter キーを押してください"
