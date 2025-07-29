#!/bin/bash
# Brewfile backup and sort script

readonly BREWFILE="${HOME}/projects/mysettings/mac/Homebrew/Brewfile"
TEMP_DIR=$(mktemp -d)
readonly TEMP_DIR

# Generate Brewfile
brew bundle dump --no-vscode --force --file "${BREWFILE}"

# Sort Brewfile by sections
while IFS= read -r line; do
  if [[ ${line} =~ ^tap ]]; then
    echo "${line}" >> "${TEMP_DIR}/tap"
  elif [[ ${line} =~ ^brew ]]; then
    echo "${line}" >> "${TEMP_DIR}/brew"
  elif [[ ${line} =~ ^cask ]]; then
    echo "${line}" >> "${TEMP_DIR}/cask"
  elif [[ ${line} =~ ^mas ]]; then
    echo "${line}" >> "${TEMP_DIR}/mas"
  fi
done < "${BREWFILE}"

# Write sorted content back to file
{
  for section in tap brew cask mas; do
    if [[ -f "${TEMP_DIR}/${section}" ]]; then
      sort "${TEMP_DIR}/${section}"
    fi
  done
} > "${BREWFILE}"

# Clean up temporary files
rm -rf "${TEMP_DIR}"

echo "✅ Brewfile updated and sorted: ${BREWFILE}"
