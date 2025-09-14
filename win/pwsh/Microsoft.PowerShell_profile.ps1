function ll { eza -lahF --time-style "+%y/%m/%d %H:%M" @args }
function claude { & "~/.local/bin/claude.exe" --dangerously-skip-permissions @args }
oh-my-posh init pwsh | Invoke-Expression
