#!/bin/zsh
# Brewfile backup and sort script

readonly BREWFILE="$HOME/projects/mysettings/mac/Homebrew/Brewfile"

# Generate Brewfile
brew bundle dump --no-vscode --force --file "$BREWFILE"

# Sort Brewfile by sections
typeset -A sections
while IFS= read -r line; do
    [[ $line =~ ^(tap|brew|cask|mas) ]] && sections[$match[1]]+="$line"$'\n'
done < "$BREWFILE"

# Write sorted content back to file
{
    for section in tap brew cask mas; do
        [[ -n $sections[$section] ]] && print -l ${(f)$(print $sections[$section] | sort)}
    done
} > "$BREWFILE"

echo "✅ Brewfile updated and sorted: $BREWFILE"
