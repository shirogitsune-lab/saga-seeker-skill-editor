# 正式スクリーンショット監査記録

この文書は実際の正式画像に対する監査結果を記録する。再生成方法は
`SCREENSHOT_WORKFLOW.md` を参照する。

## 監査条件

- 実施日: 2026-08-03
- OS: Windows 11
- 表示倍率: 100%
- Qtプラットフォーム: Windows通常表示
- Qtスタイル: Fusion
- 画像サイズ: 1440×900
- データセット: `ANON-GUIDE-001`（匿名合成データ）
- 撮影範囲: Qtウィジェット単体
- 状態生成: 実製品操作（取込プレビュー、読込、別名保存、Markdown書出し）
- 今回の更新: 20枚を再生成して差分を比較し、自動プレビュー表示で変化した
  8枚だけを更新

## 目視匿名性確認

正式画像生成後に更新する。各画像について、合成データだけであること、
利用者名・ローカルパス・デスクトップ・タスクバー・通知・他アプリがないこと、
状態と文字の判読性を確認する。

| # | ファイル | 状態 | 自動検査 | 目視匿名性 | 判読性 | 備考 |
|---:|---|---|---|---|---|---|
| 1 | `01-start-screen.png` | 起動画面 | PASS | PASS | PASS | Qtウィジェット単体 |
| 2 | `02-loaded-sheet.png` | 読込済み | PASS | PASS | PASS | 匿名名「ガイド用サンプル」、画像自動表示 |
| 3 | `03-basic-information.png` | 基本情報 | PASS | PASS | PASS | 合成プロフィール、画像自動表示 |
| 4 | `04-profile-comparison.png` | プロフィール比較 | PASS | PASS | PASS | 合成プロフィール |
| 5 | `05-skills.png` | スキル | PASS | PASS | PASS | 合成スキル |
| 6 | `06-personality-keywords.png` | 性格キーワード | PASS | PASS | PASS | 公開カタログ値 |
| 7 | `07-memories.png` | 思い出 | PASS | PASS | PASS | 合成思い出 |
| 8 | `08-markdown-import-preview.png` | Markdown取込プレビュー | PASS | PASS | PASS | 実ダイアログ、全文スクロール可 |
| 9 | `09-read-only.png` | 読み取り専用 | PASS | PASS | PASS | 匿名HTMLを実際に読込 |
| 10 | `10-save-complete.png` | 保存完了 | PASS | PASS | PASS | 固定匿名名へ実際に別名保存 |
| 11 | `11-multiple-profiles.png` | 複数プロフィール展開 | PASS | PASS | PASS | 合成プロフィール |
| 12 | `12-comparison-window.png` | 比較別ウィンドウ | PASS | PASS | PASS | ウィジェット単体 |
| 13 | `13-vacant-skill.png` | 未使用枠追加 | PASS | PASS | PASS | 合成スキル |
| 14 | `14-image-change.png` | 画像変更 | PASS | PASS | PASS | 同梱既定画像、「プレビューを再読込」 |
| 15 | `15-markdown-export.png` | Markdown書出し | PASS | PASS | PASS | 固定匿名名へ実際に書出し |
| 16 | `16-input-error.png` | 入力エラー | PASS | PASS | PASS | 合成エラー |
| 17 | `17-light-theme.png` | ライト | PASS | PASS | PASS | 合成データ |
| 18 | `18-dark-theme.png` | ダーク | PASS | PASS | PASS | 合成データ |
| 19 | `19-high-contrast-theme.png` | ハイコントラスト | PASS | PASS | PASS | 合成データ |
| 20 | `20-status-edit.png` | ステータス編集 | PASS | PASS | PASS | 合成データ |

## 監査結果

2026-08-03に20枚をWindows通常表示で再生成し、既存画像との差分を比較した。
自動プレビュー表示で変化した8枚を一覧および必要な原寸表示で目視し、差分の
なかった12枚は2026-07-31の監査済み画像を維持した。実在の人物名・キャラクター名、
利用者名、ホームディレクトリ、ローカルパス、デスクトップ、タスクバー、通知、
他アプリは写っていない。ファイル名は固定匿名名だけで、ランダムな一時パスも
表示されていない。全画像が意図した状態で判読可能であるため承認する。
