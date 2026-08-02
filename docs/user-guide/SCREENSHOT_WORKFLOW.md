# 正式スクリーンショット生成手順

この文書は再生成手順を定義する。実施日、生成環境、20画像の目視確認結果は
`SCREENSHOT_AUDIT.md` に記録する。

## 共通条件

- 実在のキャラクターシートを読み込まない。
- `scripts/generate_user_guide_screenshots.py` 内の匿名合成データだけを使う。
- 出力はアプリウィジェット単体とし、デスクトップ全体を撮影しない。
- ネイティブファイルダイアログと個人端末のSmartScreen実画面は撮影しない。
- 画像は1440×900ピクセル、PNGとする。

## 自動検査

リポジトリ直下で次を実行する。

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe scripts\generate_user_guide_screenshots.py `
  --mode offscreen --output-dir work\user-guide-offscreen
```

スクリプトは `QT_QPA_PLATFORM=offscreen` を設定し、20状態への遷移、
描画成功、全PNGの完全デコード、固定サイズ、匿名合成入力だけの利用を検査する。
20枚は一時ディレクトリで検証後にまとめて公開し、失敗時は以前の画像を保持する。
生成物は自動検査用であり、そのまま正式画像にはしない。

## 正式画像

Windows 11で表示倍率を100%にし、通常のQtプラットフォームで次を実行する。

```powershell
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
$env:QT_SCALE_FACTOR = "1"
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe scripts\generate_user_guide_screenshots.py `
  --mode formal --output-dir docs\user-guide\user-guide-assets
```

スクリプトはFusionスタイルと固定ウィンドウサイズを使い、
`QWidget.grab()` で画像を取得する。生成後は20枚すべてを目視し、
`SCREENSHOT_AUDIT.md` の各行へ結果を記録する。
取込プレビューは実ダイアログ、読み取り専用・保存完了・Markdown書出しは
匿名一時ファイルに対する実際の製品操作で状態を作る。

## 配布コピーの検証

```powershell
.\.venv\Scripts\python.exe scripts\package_user_guide.py work\guide-package
.\.venv\Scripts\python.exe -m pytest -q tests\test_user_guide.py
```

正本 `index.html` と配布版 `使い方.html` は同一バイトでなければならない。
