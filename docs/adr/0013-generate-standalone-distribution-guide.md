# ADR 0013: 配布時に自己完結型利用ガイドを生成する

- Status: Accepted
- Date: 2026-08-03

## Context

ADR 0011は保守しやすい正本として`index.html`と20枚のPNGを分離し、配布時にも同じ分離構造をコピーすると決定した。しかし`使い方.html`だけを移動したonefile利用者は画像を閲覧できず、実際のRelease添付候補もCIの検査対象になっていなかった。

正本へ巨大なBase64を保存すると画像差替えとレビューが難しくなる。一方、配布物が相対画像フォルダーへ依存すると、単体ガイドという利用者向け契約を満たせない。

## Decision

開発・保守用の正本は従来どおり分離して管理する。

```text
docs/user-guide/index.html
docs/user-guide/user-guide-assets/*.png
```

配布時だけ、HTMLのローカル画像参照を元PNGバイトのBase64 data URLへ置き換えたUTF-8の自己完結型HTMLを生成する。画像は再圧縮・変換せず、HTMLの画像参照以外を不要に再整形しない。入力HTMLと元画像は変更しない。欠損・未知・外部の画像参照は失敗とし、一時ファイルへの完全生成後に原子的に置換する。

onefile EXEへガイドを内蔵しない。Releaseではonefile EXEと同じ場所に`SagaSeekerSkillEditor-v2.0.2-guide.html`を別添付する。onedir ZIPには同一バイトのガイドを`使い方.html`として同梱し、`user-guide-assets/`を含めない。

Releaseへ添付する最終候補は次の4ファイルに固定する。

```text
SagaSeekerSkillEditor-v2.0.2-windows-x64-onefile.exe
SagaSeekerSkillEditor-v2.0.2-windows-x64-onedir.zip
SagaSeekerSkillEditor-v2.0.2-guide.html
SHA256SUMS.txt
```

組立処理は決定的なonedir ZIPを生成し、単体ガイドとZIP内ガイドの同一バイト、外部参照の不在、ZIPの安全な相対パス、必須EXE、3成果物のSHA-256を検証してから候補ディレクトリを原子的に置換する。CIはPython 3.11/3.13の公開テスト後に両形式をビルドし、この最終4ファイル集合を検査・SHAに紐づくCI artifactとして保存する。

ADR 0011の正本、正式スクリーンショット、匿名性監査に関する決定は維持する。配布時に正本HTMLと画像フォルダーをそのままコピーする決定だけを本ADRで置き換える。

## Consequences

- `使い方.html`を単独で移動しても全画像をオフライン閲覧できる。
- 正本の画像差替えとGit差分のレビュー性を維持できる。
- Release添付予定物とCI検査対象が一致する。
- 配布HTMLの容量は増えるが、画質と元画像バイトは変化しない。
