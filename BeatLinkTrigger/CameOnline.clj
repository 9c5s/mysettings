;PlayerStatus横2列表示
(swap! globals assoc :player-status-columns 2)

;PlayerStatus最前面固定
;(swap! globals assoc :player-status-always-on-top true)

;PlayerStatus自動表示
(beat-link-trigger.triggers/show-player-status)

;再生履歴自動記録
;(playlist-writer/write-playlist "G:/マイドライブ/開発/BLT" "blt_playlist" true)

;OBSオーバーレイサーバー自動起動
;(overlay/run-server)

;Carabiner自動起動
(beat-link-trigger.carabiner/show-window nil)
(beat-link-trigger.carabiner/connect)
(beat-link-trigger.carabiner/sync-mode :passive)
(beat-link-trigger.carabiner/sync-link true)
(beat-link-trigger.carabiner/align-bars true)
