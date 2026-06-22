// 配信元（dist）と API のベースURLを上書きするためのフック。
// 既定（このファイルが空＝何も代入しない）では:
//   ROOMRADAR_DIST = "/dist", ROOMRADAR_API = "/api"（同一オリジンの Flask が配信）。
//
// GitHub Pages など「静的のみ・バックエンド無し」で公開する場合は、デプロイ時に
// このファイルを次の内容で上書きする（検索だけ動作し、予約・報告は無効になる）:
//   window.ROOMRADAR_DIST = "dist";   // ページからの相対パス
//   window.ROOMRADAR_API  = "";       // 空文字＝バックエンド無し（検索のみ）
//
// 別ホストの Flask を予約バックエンドにする場合:
//   window.ROOMRADAR_API = "https://<あなたのアプリ>/api";
