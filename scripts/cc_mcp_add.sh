#!/bin/bash
# ClaudeCodeにに各種MCPサーバーを追加する設定スクリプト
claude mcp add -s user -t http deepwiki https://mcp.deepwiki.com/mcp
claude mcp add -s user -t http cloudflare-documentation https://docs.mcp.cloudflare.com/mcp
claude mcp add -s user -t stdio chrome-devtools -- bunx chrome-devtools-mcp@latest
claude mcp add -s user -t stdio drawio -- bunx @drawio/mcp
