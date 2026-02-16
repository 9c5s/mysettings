#!/bin/bash
# ClaudeCodeにに各種MCPサーバーを追加する設定スクリプト
claude mcp add -s user -t http context7 https://mcp.context7.com/mcp --header "CONTEXT7_API_KEY: ctx7sk-8ad094ff-635c-4423-963b-6809a544029b"
claude mcp add -s user -t http deepwiki https://mcp.deepwiki.com/mcp
claude mcp add -s user -t stdio playwright -- bunx @playwright/mcp@latest
claude mcp add -s user -t stdio chrome-devtools -- bunx chrome-devtools-mcp@latest
claude mcp add -s user -t stdio drawio -- bunx @drawio/mcp
