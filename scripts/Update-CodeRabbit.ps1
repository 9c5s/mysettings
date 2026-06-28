<#
.SYNOPSIS
CodeRabbit CLI インストール/アップデートスクリプト (Windows 10 SChannel TLS回避版)

.DESCRIPTION
Windows 10のSChannelがcli.coderabbit.aiの暗号スイートに非対応のため、
Node.jsのOpenSSLバックエンドを使用してダウンロードを行う。
参考: https://github.com/Sukarth/CodeRabbit-Windows/issues/1

.NOTES
前提条件: Node.js, Bun
#>

$ErrorActionPreference = 'Stop'

# --- 設定 ---
$InstallDir = Join-Path $env:LOCALAPPDATA "Programs\CodeRabbit"
$BinDir = Join-Path $InstallDir "bin"
$ExePath = Join-Path $BinDir "coderabbit.exe"
$VersionUrl = "https://cli.coderabbit.ai/releases/latest/VERSION"
$ZipUrl = "https://cli.coderabbit.ai/releases/latest/coderabbit-linux-x64.zip"

# --- バナー ---
Write-Host "==========================================" -ForegroundColor Blue
Write-Host "  CodeRabbit CLI Updater (SChannel Fix)   " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Blue

# --- 前提条件チェック ---
Write-Host "`n[*] 前提条件を確認中..."

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Error "Node.js が見つかりません。インストールしてください。"
}
Write-Host "  Node.js: $(node --version)" -ForegroundColor Gray

if (-not (Get-Command bun -ErrorAction SilentlyContinue)) {
    Write-Error "Bun が見つかりません。インストールしてください。"
}
Write-Host "  Bun:     v$(bun --version)" -ForegroundColor Gray

# --- 1. バージョン確認 (Node.js経由) ---
Write-Host "`n[*] 最新バージョンを確認中..."

$LatestVersion = (node -e "
const https = require('https');
https.get('$VersionUrl', (r) => {
    let d = '';
    r.on('data', c => d += c);
    r.on('end', () => process.stdout.write(d.trim()));
}).on('error', e => { console.error(e.message); process.exit(1); });
" 2>&1)

if ($LASTEXITCODE -ne 0) {
    Write-Error "バージョン情報の取得に失敗: $LatestVersion"
}

if (Test-Path $ExePath) {
    $CurrentVersion = (& $ExePath --version 2>&1).Trim()
    if ($CurrentVersion -eq $LatestVersion) {
        Write-Host "  最新バージョン v$CurrentVersion がインストール済みです。" -ForegroundColor Green
        Write-Host "`n更新不要です。"
        exit 0
    }
    Write-Host "  更新あり: v$CurrentVersion -> v$LatestVersion" -ForegroundColor Yellow
} else {
    Write-Host "  新規インストール: v$LatestVersion" -ForegroundColor Green
}

# --- 2. ダウンロード (Node.js経由でSChannel回避) ---
$TempDir = Join-Path $InstallDir "temp_build_$LatestVersion"
New-Item -ItemType Directory -Force -Path $TempDir | Out-Null
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

$ZipPath = Join-Path $TempDir "coderabbit-linux-x64.zip"

Write-Host "`n[*] Linux バイナリをダウンロード中 (Node.js OpenSSL)..."

node -e "
const https = require('https');
const fs = require('fs');
const url = '$ZipUrl';
const dest = process.argv[1];

function download(url, dest) {
    return new Promise((resolve, reject) => {
        const file = fs.createWriteStream(dest);
        https.get(url, (res) => {
            if (res.statusCode === 301 || res.statusCode === 302) {
                file.close();
                fs.unlinkSync(dest);
                return download(res.headers.location, dest).then(resolve).catch(reject);
            }
            if (res.statusCode !== 200) {
                file.close();
                fs.unlinkSync(dest);
                return reject(new Error('HTTP ' + res.statusCode));
            }
            const total = parseInt(res.headers['content-length'], 10);
            let downloaded = 0;
            res.on('data', (chunk) => {
                downloaded += chunk.length;
                if (total) {
                    const pct = ((downloaded / total) * 100).toFixed(0);
                    const mb = (downloaded / 1024 / 1024).toFixed(1);
                    const totalMb = (total / 1024 / 1024).toFixed(1);
                    process.stderr.write('\r  ' + pct + '% (' + mb + '/' + totalMb + ' MB)');
                }
            });
            res.pipe(file);
            file.on('finish', () => {
                file.close();
                process.stderr.write('\n');
                resolve();
            });
        }).on('error', (err) => {
            fs.unlink(dest, () => {});
            reject(err);
        });
    });
}

download(url, dest).catch(err => { console.error('Error: ' + err.message); process.exit(1); });
" "$ZipPath"

if ($LASTEXITCODE -ne 0) {
    Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Error "ダウンロードに失敗しました。"
}

Write-Host "  完了: $([math]::Round((Get-Item $ZipPath).Length / 1MB, 1)) MB" -ForegroundColor Gray

# --- 3. 展開・デコンパイル ---
Write-Host "`n[*] ZIP を展開中..."
Expand-Archive -Path $ZipPath -DestinationPath $TempDir -Force

$LinuxBinary = Join-Path $TempDir "coderabbit"
if (-not (Test-Path $LinuxBinary)) {
    Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Error "Linux バイナリが見つかりません。"
}

Write-Host "[*] バンドルをデコンパイル中..."
Push-Location $TempDir
try {
    bunx @shepherdjerred/bun-decompile coderabbit 2>&1 | Out-Null
} finally {
    Pop-Location
}

$DecompiledDir = Join-Path $TempDir "decompiled\bundled"
if (-not (Test-Path $DecompiledDir)) {
    Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Error "デコンパイルに失敗しました。"
}

# --- 4. クロスコンパイル ---
Write-Host "[*] Windows 用にコンパイル中..."
Push-Location $DecompiledDir
try {
    bun install --silent 2>&1 | Out-Null
    bun build index.js --compile --target=bun-windows-x64 --outfile="$ExePath" 2>&1 | Out-Null
} finally {
    Pop-Location
}

if (-not (Test-Path $ExePath)) {
    Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Error "コンパイルに失敗しました。"
}

Copy-Item -Path $ExePath -Destination (Join-Path $BinDir "cr.exe") -Force

# --- 5. PATH追加 (初回のみ) ---
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if (($userPath -split ';') -notcontains $BinDir) {
    $newPath = if ([string]::IsNullOrWhiteSpace($userPath)) { $BinDir } else { "$userPath;$BinDir" }
    [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')
    $env:Path = "$env:Path;$BinDir"
    Write-Host "  PATH に追加しました: $BinDir" -ForegroundColor Gray
}

# --- 6. クリーンアップ ---
Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue

# --- 完了 ---
$InstalledVersion = (& $ExePath --version 2>&1).Trim()
Write-Host "`n==========================================" -ForegroundColor Green
Write-Host "  CodeRabbit CLI v$InstalledVersion インストール完了" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host "`nターミナルを再起動後、以下を実行してください:"
Write-Host "  cr auth login" -ForegroundColor Cyan
