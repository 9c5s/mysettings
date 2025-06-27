#!/bin/bash
# Claude MCP (Model Context Protocol) に各種サーバーを追加する設定スクリプト
claude mcp add --transport http github-server https://api.githubcopilot.com/mcp -H "Authorization: Bearer $GITHUB_PAT"
claude mcp add --transport http context7 https://mcp.context7.com/mcp
claude mcp add --transport sse deepwiki https://mcp.deepwiki.com/sse
claude mcp add playwright npx @playwright/mcp@latest
