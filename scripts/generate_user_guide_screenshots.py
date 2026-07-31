"""Generate the 20 anonymous user-guide states through Qt widget capture."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
from uuid import UUID


IMAGE_SIZE = (1440, 900)
DATASET_ID = "ANON-GUIDE-001"
SCREENSHOTS = (
    "01-start-screen.png",
    "02-loaded-sheet.png",
    "03-basic-information.png",
    "04-profile-comparison.png",
    "05-skills.png",
    "06-personality-keywords.png",
    "07-memories.png",
    "08-markdown-import-preview.png",
    "09-read-only.png",
    "10-save-complete.png",
    "11-multiple-profiles.png",
    "12-comparison-window.png",
    "13-vacant-skill.png",
    "14-image-change.png",
    "15-markdown-export.png",
    "16-input-error.png",
    "17-light-theme.png",
    "18-dark-theme.png",
    "19-high-contrast-theme.png",
    "20-status-edit.png",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("offscreen", "formal"), required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def _configure_platform(mode: str) -> None:
    if mode == "offscreen":
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    else:
        os.environ.pop("QT_QPA_PLATFORM", None)
        os.environ.setdefault("QT_SCALE_FACTOR", "1")


def _run(args: argparse.Namespace) -> None:
    from PySide6.QtCore import QSettings, Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import (
        QApplication,
        QLabel,
        QMessageBox,
        QVBoxLayout,
        QWidget,
    )

    from saga_seeker_skill_editor.core.character_sheet import load_character_sheet
    from saga_seeker_skill_editor.core.markdown_interchange import (
        parse_character_markdown,
        render_ai_markdown,
    )
    from saga_seeker_skill_editor.core.phase0_candidate_sheet import (
        GenerationInputs,
        build_candidate_golden_document,
        render_candidate_html,
    )
    from saga_seeker_skill_editor.core.personality_catalog import (
        load_personality_catalog,
    )
    from saga_seeker_skill_editor.gui.main_window import (
        MainWindow,
        format_markdown_import_preview,
    )
    from saga_seeker_skill_editor.gui.theme_manager import ThemeId, ThemeManager
    from saga_seeker_skill_editor.resources import resource_path

    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    platform = QGuiApplication.platformName().casefold()
    if args.mode == "offscreen" and platform != "offscreen":
        raise RuntimeError(f"offscreen検査でQtプラットフォームが{platform!r}です")
    if args.mode == "formal" and (os.name != "nt" or platform != "windows"):
        raise RuntimeError(
            "正式画像はWindowsの通常Qtプラットフォームでだけ生成できます"
        )

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    for stale in output_dir.glob("*.png"):
        if stale.name not in SCREENSHOTS:
            stale.unlink()

    settings = QSettings(
        str(output_dir / ".screenshot-settings.ini"),
        QSettings.Format.IniFormat,
    )
    theme_manager = ThemeManager(app, settings=settings)

    icon_bytes = resource_path("assets/カナリア.webp").read_bytes()
    generation = GenerationInputs(
        uuid_factory=lambda: UUID("123e4567-e89b-42d3-a456-426614174000"),
        clock=lambda: datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc),
        local_timezone=timezone.utc,
    )
    document = build_candidate_golden_document(
        icon_webp=icon_bytes,
        generation=generation,
    )
    data = document["data"]
    assert isinstance(data, dict)
    data["name"] = "ガイド用サンプル"
    data["profile"] = {
        "basicSettings": "港町で依頼を受ける探索者。\n仲間の安全を最優先にする。",
        "appearance": "青い外套と小さな方位磁針を身につけている。",
        "personality": "慎重だが、困っている人を見過ごせない。",
        "speechStyle": "落ち着いた口調。結論から短く話す。",
        "background": "地図職人の家で育ち、遺跡調査の技術を学んだ。",
        "talentsAndRole": "調査、危険察知、仲間の支援。",
        "otherFeatures": "温かい飲み物を淹れるのが得意。",
    }
    data["status"] = {
        "strength": "C",
        "endurance": "B",
        "intelligence": "A",
        "mentalStrength": "B",
        "agility": "C",
        "charm": "E",
        "luck": "D",
    }
    data["skills"] = [
        {
            "id": "guide-skill-1",
            "name": "道標のひらめき",
            "description": "周囲の手がかりを整理し、安全な進路を見つける。",
            "type": "",
            "key": "",
        },
        {
            "id": "guide-skill-2",
            "name": "静かな観察",
            "description": "小さな変化を見落とさず、危険の兆候を伝える。",
            "type": "",
            "key": "",
        },
    ]
    data["personalities"] = [
        {"id": 1, "name": "勇敢", "type": "力", "karma": "美徳"},
        {"id": 7, "name": "前向き", "type": "力", "karma": "美徳"},
    ]
    data["memories"] = [
        {
            "id": "memory-guide-1",
            "title": "初めて完成させた地図",
            "summary": "仲間と協力して港の古い水路を調べた。",
            "location": "合成港",
            "intent": "安全な通路を見つける",
            "outcome": "新しい近道を発見した",
            "tags": ["調査", "仲間"],
            "isPlaceholder": False,
        }
    ]
    sheet = load_character_sheet(render_candidate_html(document))
    catalog = load_personality_catalog()
    markdown_plan = parse_character_markdown(
        render_ai_markdown(sheet),
        catalog=catalog,
    )

    def new_window(theme: ThemeId = ThemeId.LIGHT, *, loaded: bool = True):
        theme_manager.apply_theme(theme, persist=False)
        window = MainWindow(theme_manager=theme_manager)
        window.resize(*IMAGE_SIZE)
        if loaded:
            window._apply_sheet(None, sheet)
        return window

    def stage_message(title: str, text_value: str, *, critical: bool = False):
        stage = QWidget()
        stage.setObjectName("screenshotStage")
        stage.resize(*IMAGE_SIZE)
        layout = QVBoxLayout(stage)
        layout.setContentsMargins(220, 100, 220, 100)
        backdrop = QLabel("Saga & Seeker キャラクターシートエディター")
        backdrop.setAlignment(Qt.AlignmentFlag.AlignCenter)
        backdrop.setObjectName("characterName")
        box = QMessageBox(stage)
        box.setWindowFlags(Qt.WindowType.Widget)
        box.setIcon(
            QMessageBox.Icon.Critical if critical else QMessageBox.Icon.Information
        )
        box.setWindowTitle(title)
        box.setText(title)
        box.setInformativeText(text_value)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        layout.addWidget(backdrop)
        layout.addWidget(box, 1)
        return stage

    def capture(name: str, widget: QWidget) -> None:
        widget.resize(*IMAGE_SIZE)
        widget.show()
        app.processEvents()
        pixmap = widget.grab()
        if pixmap.width() != IMAGE_SIZE[0] or pixmap.height() != IMAGE_SIZE[1]:
            raise RuntimeError(
                f"{name}: 画像サイズが{pixmap.width()}x{pixmap.height()}です"
            )
        target = output_dir / name
        if not pixmap.save(str(target), "PNG"):
            raise RuntimeError(f"{name}: PNG保存に失敗しました")
        widget.hide()
        widget.deleteLater()
        app.processEvents()

    capture(SCREENSHOTS[0], new_window(loaded=False))

    window = new_window()
    capture(SCREENSHOTS[1], window)

    window = new_window()
    window.edit_tabs.setCurrentIndex(window.basic_tab_index)
    capture(SCREENSHOTS[2], window)

    window = new_window()
    window.edit_tabs.setCurrentIndex(window.basic_tab_index)
    window.character_details_editor.show_profile_comparison()
    capture(SCREENSHOTS[3], window)

    window = new_window()
    window.edit_tabs.setCurrentIndex(window.skill_tab_index)
    window.skill_list.setCurrentItem(window.skill_list.topLevelItem(0))
    capture(SCREENSHOTS[4], window)

    window = new_window()
    window.edit_tabs.setCurrentIndex(window.personality_tab_index)
    window.personality_editor.search_edit.setText("勇")
    capture(SCREENSHOTS[5], window)

    window = new_window()
    window.edit_tabs.setCurrentIndex(window.memory_tab_index)
    capture(SCREENSHOTS[6], window)

    capture(
        SCREENSHOTS[7],
        stage_message(
            "Markdown取込プレビュー",
            format_markdown_import_preview(markdown_plan)
            + "\n\nこの内容で新規作成しますか？",
        ),
    )

    window = new_window()
    window.read_only_badge.setVisible(True)
    window.status_label.setText("△ 読み取り専用")
    window.status_detail_label.setText(
        "構造差異があるため、内容を表示したまま保存を停止しています"
    )
    window.character_details_editor.name_edit.setReadOnly(True)
    for edit in window.character_details_editor.profile_edits.values():
        edit.setReadOnly(True)
    capture(SCREENSHOTS[8], window)

    window = new_window()
    window.status_label.setText("✓ 保存完了")
    window.status_detail_label.setText(
        "匿名サンプルを別名で保存しました。元ファイルは変更していません"
    )
    window.file_label.setText("ガイド用サンプル_保存済み.html")
    capture(SCREENSHOTS[9], window)

    window = new_window()
    window.edit_tabs.setCurrentIndex(window.basic_tab_index)
    for key in ("basicSettings", "appearance", "background"):
        window.character_details_editor.profile_toggles[key].setChecked(True)
    capture(SCREENSHOTS[10], window)

    window = new_window()
    window.edit_tabs.setCurrentIndex(window.basic_tab_index)
    window.character_details_editor.open_profile_comparison()
    app.processEvents()
    comparison = window.character_details_editor.comparison_window
    if comparison is None:
        raise RuntimeError("プロフィール比較の別ウィンドウを開けません")
    comparison.resize(*IMAGE_SIZE)
    capture(SCREENSHOTS[11], comparison)
    window.hide()
    window.deleteLater()

    window = new_window()
    window.edit_tabs.setCurrentIndex(window.skill_tab_index)
    window.skill_list.setCurrentItem(window.skill_list.topLevelItem(2))
    vacant = window.skill_widgets[2]
    vacant.name_edit.setText("新しい合成スキル")
    vacant.description_edit.setPlainText("未使用枠へ安全に追加する例です。")
    capture(SCREENSHOTS[12], window)

    window = new_window()
    window.edit_tabs.setCurrentIndex(window.basic_tab_index)
    window.character_details_editor.show_icon_preview()
    window.character_details_editor.replace_icon_button.setFocus()
    capture(SCREENSHOTS[13], window)

    capture(
        SCREENSHOTS[14],
        stage_message(
            "Markdown書出し完了",
            "AI向けMarkdown形式 v2を書き出しました。\n"
            "画像と内部IDは含まれません。実在の保存先パスはガイド画像へ表示しません。",
        ),
    )

    capture(
        SCREENSHOTS[15],
        stage_message(
            "入力エラー",
            "スキル名に改行を含めることはできません。\n"
            "入力内容は変更されていません。改行を除いてから再度確認してください。",
            critical=True,
        ),
    )

    window = new_window(ThemeId.LIGHT)
    window.edit_tabs.setCurrentIndex(window.skill_tab_index)
    capture(SCREENSHOTS[16], window)

    window = new_window(ThemeId.DARK)
    window.edit_tabs.setCurrentIndex(window.skill_tab_index)
    capture(SCREENSHOTS[17], window)

    window = new_window(ThemeId.HIGH_CONTRAST)
    window.edit_tabs.setCurrentIndex(window.skill_tab_index)
    capture(SCREENSHOTS[18], window)

    window = new_window(ThemeId.LIGHT)
    window.edit_tabs.setCurrentIndex(window.status_tab_index)
    window.status_editor.rank_boxes["luck"].setCurrentText("A")
    capture(SCREENSHOTS[19], window)

    settings_file = output_dir / ".screenshot-settings.ini"
    if settings_file.exists():
        settings_file.unlink()
    generated = sorted(path.name for path in output_dir.glob("*.png"))
    if generated != sorted(SCREENSHOTS):
        raise RuntimeError("20状態のファイル集合が一致しません")
    print(
        f"{args.mode}: {len(generated)} images, "
        f"{IMAGE_SIZE[0]}x{IMAGE_SIZE[1]}, dataset={DATASET_ID}"
    )


def main() -> int:
    args = _parse_args()
    _configure_platform(args.mode)
    try:
        _run(args)
    except Exception as exc:
        print(f"screenshot generation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
