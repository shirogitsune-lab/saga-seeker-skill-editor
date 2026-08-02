from __future__ import annotations

import importlib.util
from pathlib import Path

from saga_seeker_skill_editor.core.character_sheet import load_character_sheet


ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    path = ROOT / "scripts" / "generate_manual_game_check.py"
    spec = importlib.util.spec_from_file_location("generate_manual_game_check", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manual_game_fixture_is_anonymous_and_preserves_profile_newlines(
    tmp_path: Path,
) -> None:
    module = _load_module()
    html_path, checklist_path = module.generate(tmp_path)

    sheet = load_character_sheet(html_path.read_bytes())
    assert sheet.character_name == "匿名改行確認"
    assert (
        sheet.data["data"]["profile"]["basicSettings"]
        == module.EXPECTED_PROFILE
    )
    assert (
        "&lt;探索者&gt; &amp; 仲間<br>".encode("utf-8")
        in html_path.read_bytes()
    )
    checklist = checklist_path.read_text(encoding="utf-8")
    assert "実在のキャラクターデータは含みません" in checklist
    assert "C:\\" not in checklist
