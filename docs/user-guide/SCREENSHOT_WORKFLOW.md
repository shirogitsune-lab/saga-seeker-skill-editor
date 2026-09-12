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

## 配布用ガイド

編集用の正本は `docs/user-guide/index.html` と `user-guide-assets/` に分けて管理する。
利用者へ配布するガイドは、必ず `scripts/package_user_guide.py` を通して生成する。

```powershell
.\.venv\Scripts\python.exe scripts\package_user_guide.py work\guide-package
.\.venv\Scripts\python.exe -m pytest -q tests\test_user_guide.py
```

生成される `使い方.html` は、20枚の画像をすべてHTML内へ埋め込んだ自己完結ファイルでなければならない。
`user-guide-assets/` などの外部画像フォルダを配布先で必要とする状態にはしない。

`onedir` 版と `onefile` 版のどちらを利用する場合も、利用者へ渡す使い方ガイドは同じ自己完結HTMLとする。
配布物へ正本の `index.html` をそのままコピーせず、必ずパッケージ処理を経た単体HTMLを使用する。
