from __future__ import annotations

import html
import json

from saga_seeker_skill_editor.core.html_li_patcher import LiTextPatch, patch_simple_skill_li
from saga_seeker_skill_editor.core.html_locator import find_direct_skill_lis, find_unique_skills_ul, text_content
from saga_seeker_skill_editor.core.json_token_patcher import replace_string_fields_in_object
from saga_seeker_skill_editor.core.script_safe_json import dumps_script_safe_string


def test_script_safe_json_string_escapes_script_terminator_surface() -> None:
    token = dumps_script_safe_string('x</script><div data-a="&">')

    assert b"</script>" not in token.lower()
    assert b"\\u003c/script\\u003e" in token.lower()
    assert b"\\u0026" in token
    assert json.loads(token.decode("utf-8")) == 'x</script><div data-a="&">'


def test_json_token_patcher_replaces_only_named_string_tokens() -> None:
    original = (
        b'{\n'
        b'  "id": "skill_no01_2025-12-30-05-02",\n'
        b'  "name": "Old",\n'
        b'  "description": "Old desc",\n'
        b'  "type": "",\n'
        b'  "key": "",\n'
        b'  "unknown": {"name": "Nested must stay"}\n'
        b"}"
    )

    patched = replace_string_fields_in_object(
        original,
        {"name": "New </script>", "description": "A&B"},
    )

    assert b'"id": "skill_no01_2025-12-30-05-02"' in patched
    assert b'"unknown": {"name": "Nested must stay"}' in patched
    assert b"</script>" not in patched.lower()
    parsed = json.loads(patched.decode("utf-8"))
    assert parsed["name"] == "New </script>"
    assert parsed["description"] == "A&B"


def test_li_patcher_uses_attribute_and_text_escaping_contexts() -> None:
    name = 'Name "double" \'single\' & <tag>\n\t\\ 日本語 😀'
    description = 'Desc "double" \'single\' & <tag>\n\t\\ 日本語 😀'
    raw = (
        '<ul id="skills-value">'
        '<li class="keep" data-skill-id="sk1" data-skill-name="Old" data-extra="stay" '
        'data-skill-type="" data-skill-description="Old desc">Old</li>'
        '</ul>'
    ).encode("utf-8")
    ul = find_unique_skills_ul(raw)
    li = find_direct_skill_lis(raw, ul)[0]

    patched = patch_simple_skill_li(raw, li, LiTextPatch(name=name, description=description))
    patched_li = find_direct_skill_lis(patched, find_unique_skills_ul(patched))[0]

    assert patched_li.attrs["data-extra"] == "stay"
    assert patched_li.attrs["data-skill-name"] == name
    assert patched_li.attrs["data-skill-description"] == description
    assert text_content(patched_li.inner) == name
    assert html.unescape(patched_li.inner.decode("utf-8")) == name
