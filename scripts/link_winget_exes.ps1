# 管理者権限チェックと自動昇格
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
  Write-Host "管理者権限が必要です。昇格して再実行します..." -ForegroundColor Yellow
  Start-Process pwsh.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
  exit
}

# ソースディレクトリとターゲットディレクトリの設定 (環境変数を使用)
$sourceDir = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
$destDir = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links"

# ターゲットディレクトリが存在しない場合は作成
if (-not (Test-Path -Path $destDir)) {
  Write-Host "ターゲットディレクトリを作成しています: $destDir"
  New-Item -ItemType Directory -Path $destDir -Force | Out-Null
}

# ソースディレクトリ内の全ての.exeファイルを再帰的に検索
Write-Host "exeファイルを検索しています: $sourceDir"
$exeFiles = Get-ChildItem -Path $sourceDir -Recurse -Filter "*.exe"

if ($exeFiles.Count -eq 0) {
  Write-Warning "exeファイルが見つかりませんでした。"
  exit
}

# 検出されたファイルを表示
Write-Host "--- 検出されたexeファイル一覧 ($($exeFiles.Count)件) ---" -ForegroundColor Cyan
$exeFiles | Select-Object -ExpandProperty Name
Write-Host "----------------------------------------" -ForegroundColor Cyan

# デフォルトでは全てのファイルを対象とする
$targetFiles = $exeFiles

# 除外確認
$response = Read-Host "除外したいファイルはありますか？ (y/n)"
if ($response -eq 'y') {
  Write-Host "ポップアップウィンドウで【除外したい】ファイルを選択してください..." -ForegroundColor Cyan
  Write-Host "※ CtrlキーやShiftキーを押しながらクリックで複数選択できます。"

  # ユーザーに除外するファイルを選択させる
  $excludedFiles = $exeFiles | Select-Object Name, DirectoryName, FullName | Out-GridView -Title "除外するexeファイルを選択してください (キャンセルで除外なし)" -PassThru

  if ($excludedFiles) {
    # 選択されたファイルを除外リストとして、対象リストをフィルタリング
    $excludedFullNames = $excludedFiles.FullName
    $targetFiles = $exeFiles | Where-Object { $excludedFullNames -notcontains $_.FullName }
    Write-Host "$($excludedFiles.Count) 個のファイルを除外しました。" -ForegroundColor Yellow
  }
}
else {
  Write-Host "全てのファイルをリンクします。"
}

if ($targetFiles.Count -eq 0) {
  Write-Host "リンク対象のファイルがありません。処理を終了します。" -ForegroundColor Yellow
  exit
}

foreach ($file in $targetFiles) {
  # リンク先のパスを作成
  $linkPath = Join-Path -Path $destDir -ChildPath $file.Name

  # リンクが既に存在するか確認
  if (Test-Path -Path $linkPath) {
    Write-Host "スキップ (リンク済): $($file.Name)" -ForegroundColor Yellow
    continue
  }

  try {
    # シンボリックリンクの作成
    # 注意: シンボリックリンクの作成には管理者権限が必要な場合があります (開発者モードが無効な場合)
    New-Item -ItemType SymbolicLink -Path $linkPath -Target $file.FullName -ErrorAction Stop | Out-Null
    Write-Host "リンク作成: $($file.Name) -> $($file.FullName)" -ForegroundColor Green
  }
  catch {
    Write-Error "リンク作成エラー ($($file.Name)): $_"
  }
}

Write-Host "処理が完了しました。" -ForegroundColor Cyan
Read-Host "終了するには Enter キーを押してください"
