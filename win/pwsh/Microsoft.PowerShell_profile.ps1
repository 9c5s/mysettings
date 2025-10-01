# コマンドエイリアス
function ll { eza -lahF --time-style "+%y/%m/%d %H:%M" @args }
function claude { & "~/.local/bin/claude.exe" --dangerously-skip-permissions @args }

# oh-my-posh設定
oh-my-posh init pwsh --config 'https://raw.githubusercontent.com/JanDeDobbeleer/oh-my-posh/main/themes/emodipt-extend.omp.json' | Invoke-Expression

# uv/uvx自動補完
(& uv generate-shell-completion powershell) | Out-String | Invoke-Expression
(& uvx --generate-shell-completion powershell) | Out-String | Invoke-Expression

# PowerToys CommandNotFound module
Import-Module -Name Microsoft.WinGet.CommandNotFound
