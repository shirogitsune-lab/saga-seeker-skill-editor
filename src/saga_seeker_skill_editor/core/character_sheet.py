"""Character sheet loading and position-based skill mapping."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import html
from typing import Any
import json

from saga_seeker_skill_editor.core.html_locator import (
    ElementSpan,
    HtmlStructureError,
    LiSpan,
    StartTagSpan,
    find_direct_skill_lis,
    find_direct_personality_lis,
    find_direct_lis,
    find_unique_descendant_by_attrs,
    find_unique_abilities_ul,
    find_unique_element_by_id,
    find_unique_memories_ul,
    find_unique_start_tag_by_id,
    find_unique_script_json,
    find_unique_personality_ul,
    find_unique_skills_ul,
    text_content,
)
from saga_seeker_skill_editor.core.html_li_patcher import (
    build_new_memory_li,
    build_patched_memory_li_fields,
    build_patched_start_tag_attr,
)
from saga_seeker_skill_editor.core.personality_catalog import (
    PersonalityCatalogError,
    catalog_by_id,
    load_personality_catalog,
)
from saga_seeker_skill_editor.core.phase0_candidate_sheet import (
    GenerationInputs,
    build_candidate_golden_document,
    format_memory_id,
    make_empty_placeholder_memory,
    render_candidate_html,
)
from saga_seeker_skill_editor.core.json_span import (
    JsonSpanError,
    JsonValueSpan,
    find_object_key_value,
    locate_data_object_array,
)
from saga_seeker_skill_editor.core.json_token_patcher import (
    JsonPatchError,
    replace_value_fields_in_object,
)
from saga_seeker_skill_editor.core.script_safe_json import (
    dumps_script_safe,
    dumps_script_safe_string,
)
from saga_seeker_skill_editor.core.skill_classifier import (
    SkillClassification,
    classify_skill,
    duplicate_string_ids,
)


class CharacterSheetError(ValueError):
    """Raised when a character sheet cannot be safely interpreted."""


class CharacterSheetRenderError(ValueError):
    """Raised when a v2 draft cannot be rendered without risking source bytes."""


PROFILE_TABS = (
    ("basicSettings", "Basic Settings"),
    ("appearance", "Appearance"),
    ("personality", "Personality"),
    ("speechStyle", "Speaking Style"),
    ("background", "Background"),
    ("talentsAndRole", "Special Skills & Role"),
    ("otherFeatures", "Other Traits"),
)
STATUS_HTML_FIELDS = (
    ("strength", "Strength"),
    ("endurance", "Endurance"),
    ("intelligence", "Intelligence"),
    ("mentalStrength", "Willpower"),
    ("agility", "Agility"),
    ("luck", "Luck"),
)
STATUS_RANKS = {"E": 1, "D": 2, "C": 3, "B": 4, "A": 5, "S": 6}


@dataclass(frozen=True)
class SkillEntry:
    index: int
    skill: dict[str, Any]
    li: LiSpan
    position_consistent: bool
    classification: SkillClassification


@dataclass(frozen=True)
class PersonalityEntry:
    index: int
    keyword: dict[str, Any]
    li: LiSpan


@dataclass(frozen=True)
class StatusEntry:
    key: str
    rank: str
    li: LiSpan
    rank_span: ElementSpan
    gauge_lis: tuple[LiSpan, ...]


@dataclass(frozen=True)
class MemoryEntry:
    index: int
    memory: dict[str, Any]
    is_placeholder: bool
    html_li: LiSpan | None


@dataclass(frozen=True)
class SectionDiagnosticBaseline:
    """Load-time safety facts that a later save must not worsen."""

    name: str
    editable: bool
    diagnostic_codes: tuple[str, ...] = ()
    severity: str = "none"
    json_count: int | None = None
    html_count: int | None = None
    position_consistent: bool | None = None
    json_bytes: bytes = b""
    html_bytes: bytes = b""
    read_only_reason: str = ""


@dataclass(frozen=True)
class DiagnosticBaseline:
    """Immutable collection of per-section load diagnostics."""

    sections: tuple[SectionDiagnosticBaseline, ...] = ()

    @property
    def section_names(self) -> tuple[str, ...]:
        return tuple(section.name for section in self.sections)

    def for_section(self, name: str) -> SectionDiagnosticBaseline:
        for section in self.sections:
            if section.name == name:
                return section
        raise KeyError(name)


@dataclass(frozen=True)
class CharacterSheet:
    raw_html: bytes
    data: dict[str, Any]
    script_span: ElementSpan
    skills_ul_span: ElementSpan
    entries: list[SkillEntry]
    vacant_lis: list[LiSpan]
    slot_count: int
    vacant_slot_count: int
    read_only: bool
    read_only_reason: str = ""
    personality_ul_span: ElementSpan | None = None
    personality_entries: tuple[PersonalityEntry, ...] = ()
    personality_lis: tuple[LiSpan, ...] = ()
    personality_slot_count: int = 0
    personality_read_only: bool = True
    personality_read_only_reason: str = "性格キーワード欄を確認できません"
    format_version: object = None
    whole_sheet_read_only: bool = False
    diagnostic_baseline: DiagnosticBaseline = DiagnosticBaseline()
    name_span: ElementSpan | None = None
    profile_spans: tuple[tuple[str, ElementSpan], ...] = ()
    status_entries: tuple[tuple[str, StatusEntry], ...] = ()
    memory_entries: tuple[MemoryEntry, ...] = ()
    icon_span: StartTagSpan | None = None

    @property
    def character_name(self) -> str:
        data = self.data.get("data")
        if isinstance(data, dict) and isinstance(data.get("name"), str):
            return data["name"]
        return ""


@dataclass
class CharacterSheetDraft:
    """Sparse user edits relative to one successfully loaded byte baseline."""

    _baseline_raw: bytes
    _baseline_values: dict[tuple[object, ...], object]
    _edits: dict[tuple[object, ...], object] = field(default_factory=dict)
    _memory_order: tuple[int, ...] = ()
    _baseline_memory_count: int = 0
    _memory_replacements: dict[int, dict[str, Any]] = field(default_factory=dict)
    _new_memories: dict[int, dict[str, Any]] = field(default_factory=dict)
    _next_new_memory_token: int = -1
    _icon_replacement: tuple[str, str] | None = None

    @classmethod
    def from_sheet(cls, sheet: CharacterSheet) -> CharacterSheetDraft:
        data = sheet.data.get("data")
        profile = data.get("profile") if isinstance(data, dict) else None
        baseline_values = {("data", "name"): sheet.character_name}
        if isinstance(profile, dict):
            baseline_values.update(
                {
                    ("data", "profile", key): value
                    for key, value in profile.items()
                    if isinstance(key, str) and isinstance(value, str)
                }
            )
        status = data.get("status") if isinstance(data, dict) else None
        if isinstance(status, dict):
            baseline_values.update(
                {
                    ("data", "status", key): value
                    for key, value in status.items()
                    if isinstance(key, str) and isinstance(value, str)
                }
            )
        icon = data.get("icon") if isinstance(data, dict) else None
        if isinstance(icon, dict):
            baseline_values.update(
                {
                    ("data", "icon", key): value
                    for key, value in icon.items()
                    if isinstance(key, str)
                }
            )
        memories = data.get("memories") if isinstance(data, dict) else None
        if isinstance(memories, list):
            for index, memory in enumerate(memories):
                if not isinstance(memory, dict):
                    continue
                baseline_values.update(
                    {
                        ("data", "memories", index, key): value
                        for key, value in memory.items()
                        if isinstance(key, str)
                    }
                )
        return cls(
            _baseline_raw=sheet.raw_html,
            _baseline_values=baseline_values,
            _memory_order=tuple(range(len(sheet.memory_entries))),
            _baseline_memory_count=len(sheet.memory_entries),
        )

    @property
    def has_changes(self) -> bool:
        return (
            bool(self._edits)
            or bool(self._memory_replacements)
            or bool(self._new_memories)
            or self._icon_replacement is not None
            or self._memory_order != tuple(range(self._baseline_memory_count))
        )

    @property
    def memory_order(self) -> tuple[int, ...]:
        """Return stable source tokens in the current UI order."""

        return self._memory_order

    def memory_value(self, token: int) -> dict[str, Any]:
        """Return a copy of the current memory represented by one source token."""

        if token in self._new_memories:
            return dict(self._new_memories[token])
        if token in self._memory_replacements:
            return dict(self._memory_replacements[token])
        values = {
            path[3]: value
            for path, value in self._baseline_values.items()
            if len(path) == 4
            and path[1] == "memories"
            and path[2] == token
        }
        if not values:
            raise IndexError("memory token is unavailable")
        for path, value in self._edits.items():
            if (
                len(path) == 4
                and path[1] == "memories"
                and path[2] == token
            ):
                values[path[3]] = value
        return values

    def set_name(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError("character name must be a string")
        path = ("data", "name")
        if value == self._baseline_values[path]:
            self._edits.pop(path, None)
        else:
            self._edits[path] = value

    def set_profile(self, key: str, value: str) -> None:
        if key not in dict(PROFILE_TABS):
            raise KeyError(key)
        if not isinstance(value, str):
            raise TypeError("profile value must be a string")
        path = ("data", "profile", key)
        if path not in self._baseline_values:
            raise CharacterSheetRenderError(f"profile field {key!r} is unavailable")
        if value == self._baseline_values[path]:
            self._edits.pop(path, None)
        else:
            self._edits[path] = value

    def set_status(self, key: str, value: str) -> None:
        if key not in {field for field, _label in STATUS_HTML_FIELDS}:
            raise KeyError(key)
        if value not in STATUS_RANKS:
            raise ValueError(f"unsupported status rank: {value!r}")
        path = ("data", "status", key)
        if path not in self._baseline_values:
            raise CharacterSheetRenderError(f"status field {key!r} is unavailable")
        if value == self._baseline_values[path]:
            self._edits.pop(path, None)
        else:
            self._edits[path] = value

    def set_memory_field(self, index: int, field: str, value: str) -> None:
        if field not in {"title", "summary", "location", "intent", "outcome"}:
            raise KeyError(field)
        if not isinstance(value, str):
            raise TypeError("memory field value must be a string")
        mutable_memory = self._mutable_memory_for_token(index)
        if mutable_memory is not None:
            if mutable_memory.get("isPlaceholder") is True:
                raise CharacterSheetRenderError(
                    "placeholder memories must be converted first"
                )
            mutable_memory[field] = value
            return
        path = ("data", "memories", index, field)
        if path not in self._baseline_values:
            raise CharacterSheetRenderError(
                f"memory {index + 1} field {field!r} is unavailable"
            )
        placeholder_path = ("data", "memories", index, "isPlaceholder")
        if self._baseline_values.get(placeholder_path) is True:
            raise CharacterSheetRenderError("placeholder memories must be converted first")
        if value == self._baseline_values[path]:
            self._edits.pop(path, None)
        else:
            self._edits[path] = value

    def set_memory_tags(self, index: int, tags: list[str]) -> None:
        if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
            raise TypeError("memory tags must be a list of strings")
        mutable_memory = self._mutable_memory_for_token(index)
        if mutable_memory is not None:
            if mutable_memory.get("isPlaceholder") is True:
                raise CharacterSheetRenderError(
                    "placeholder memories must be converted first"
                )
            mutable_memory["tags"] = list(tags)
            return
        path = ("data", "memories", index, "tags")
        if path not in self._baseline_values:
            raise CharacterSheetRenderError(
                f"memory {index + 1} tags are unavailable"
            )
        placeholder_path = ("data", "memories", index, "isPlaceholder")
        if self._baseline_values.get(placeholder_path) is True:
            raise CharacterSheetRenderError("placeholder memories must be converted first")
        if tags == self._baseline_values[path]:
            self._edits.pop(path, None)
        else:
            self._edits[path] = list(tags)

    def move_memory(self, from_position: int, to_position: int) -> None:
        count = len(self._memory_order)
        if not 0 <= from_position < count or not 0 <= to_position < count:
            raise IndexError("memory position is out of range")
        order = list(self._memory_order)
        item = order.pop(from_position)
        order.insert(to_position, item)
        self._memory_order = tuple(order)

    def remove_memory(self, position: int) -> None:
        if not 0 <= position < len(self._memory_order):
            raise IndexError("memory position is out of range")
        order = list(self._memory_order)
        source_index = order.pop(position)
        self._memory_order = tuple(order)
        self._memory_replacements.pop(source_index, None)
        self._new_memories.pop(source_index, None)
        self._edits = {
            path: value
            for path, value in self._edits.items()
            if not (
                len(path) == 4
                and path[1] == "memories"
                and path[2] == source_index
            )
        }

    def convert_placeholder_to_normal(
        self,
        index: int,
        *,
        generation: GenerationInputs,
    ) -> None:
        current_memory = self.memory_value(index)
        if current_memory.get("isPlaceholder") is not True:
            raise CharacterSheetRenderError("only placeholder memories can be converted")
        now = generation.clock()
        if now.tzinfo is None:
            raise CharacterSheetRenderError("clock must return an aware datetime")
        existing_ids = {
            value
            for path, value in self._baseline_values.items()
            if len(path) == 4
            and path[1] == "memories"
            and path[3] == "id"
            and isinstance(value, str)
            and value
        }
        existing_ids.update(
            memory["id"]
            for memory in (
                *self._memory_replacements.values(),
                *self._new_memories.values(),
            )
            if isinstance(memory.get("id"), str) and memory["id"]
        )
        memory_id = ""
        for _attempt in range(100):
            memory_id = format_memory_id(
                generation.uuid_factory(),
                local_date=now.astimezone(generation.local_timezone),
            )
            if memory_id not in existing_ids:
                break
        else:
            raise CharacterSheetRenderError("could not generate an unused memory ID")
        converted = {
            "id": memory_id,
            "title": "",
            "summary": "",
            "location": "",
            "intent": "",
            "outcome": "",
            "tags": [],
            "isPlaceholder": False,
        }
        if index in self._new_memories:
            self._new_memories[index] = converted
        else:
            self._memory_replacements[index] = converted

    def replace_memory_with_placeholder(self, index: int) -> None:
        current_memory = self.memory_value(index)
        if current_memory.get("isPlaceholder") is not False:
            raise CharacterSheetRenderError(
                "only normal memories can be replaced with a placeholder"
            )
        replacement = make_empty_placeholder_memory()
        if index in self._new_memories:
            self._new_memories[index] = replacement
        elif self._baseline_values.get(
            ("data", "memories", index, "isPlaceholder")
        ) is True:
            self._memory_replacements.pop(index, None)
        else:
            self._memory_replacements[index] = replacement
            self._edits = {
                path: value
                for path, value in self._edits.items()
                if not (
                    len(path) == 4
                    and path[1] == "memories"
                    and path[2] == index
                )
            }

    def add_normal_memory(self, *, generation: GenerationInputs) -> int:
        if len(self._memory_order) >= 15:
            raise CharacterSheetRenderError("memory count limit of 15 has been reached")
        now = generation.clock()
        if now.tzinfo is None:
            raise CharacterSheetRenderError("clock must return an aware datetime")
        existing_ids = {
            value
            for path, value in self._baseline_values.items()
            if len(path) == 4
            and path[1] == "memories"
            and path[3] == "id"
            and isinstance(value, str)
            and value
        }
        existing_ids.update(
            memory["id"]
            for memory in (*self._memory_replacements.values(), *self._new_memories.values())
            if isinstance(memory.get("id"), str) and memory["id"]
        )
        memory_id = ""
        for _attempt in range(100):
            memory_id = format_memory_id(
                generation.uuid_factory(),
                local_date=now.astimezone(generation.local_timezone),
            )
            if memory_id not in existing_ids:
                break
        else:
            raise CharacterSheetRenderError("could not generate an unused memory ID")
        token = self._next_new_memory_token
        self._next_new_memory_token -= 1
        self._new_memories[token] = {
            "id": memory_id,
            "title": "",
            "summary": "",
            "location": "",
            "intent": "",
            "outcome": "",
            "tags": [],
            "isPlaceholder": False,
        }
        self._memory_order = (*self._memory_order, token)
        return token

    def fill_placeholder_memories(self) -> int:
        add_count = max(0, 15 - len(self._memory_order))
        for _index in range(add_count):
            token = self._next_new_memory_token
            self._next_new_memory_token -= 1
            self._new_memories[token] = make_empty_placeholder_memory()
            self._memory_order = (*self._memory_order, token)
        return add_count

    def set_icon_webp(self, webp_bytes: bytes) -> None:
        if not isinstance(webp_bytes, bytes) or not webp_bytes:
            raise TypeError("processed WebP must be non-empty bytes")
        if len(webp_bytes) > 64 * 1024 * 1024:
            raise CharacterSheetRenderError("processed WebP exceeds 64 MiB")
        data_uri = (
            "data:image/webp;base64,"
            + base64.b64encode(webp_bytes).decode("ascii")
        )
        baseline_mime = self._baseline_values.get(("data", "icon", "mime"))
        baseline_uri = self._baseline_values.get(("data", "icon", "dataUri"))
        if baseline_mime == "image/webp" and baseline_uri == data_uri:
            self._icon_replacement = None
        else:
            self._icon_replacement = ("image/webp", data_uri)

    def _mutable_memory_for_token(self, token: int) -> dict[str, Any] | None:
        if token in self._new_memories:
            return self._new_memories[token]
        if token in self._memory_replacements:
            return self._memory_replacements[token]
        return None


def render_character_sheet(sheet: CharacterSheet, draft: CharacterSheetDraft) -> bytes:
    """Render a sparse draft, returning the original object when unchanged."""

    if draft._baseline_raw != sheet.raw_html:
        raise CharacterSheetRenderError("draft does not belong to this sheet baseline")
    if not draft.has_changes:
        return sheet.raw_html
    if sheet.whole_sheet_read_only:
        raise CharacterSheetRenderError("unknown formatVersion sheets cannot be edited")
    supported_paths = {
        ("data", "name"),
        *(("data", "profile", key) for key, _tab in PROFILE_TABS),
        *(("data", "status", key) for key, _label in STATUS_HTML_FIELDS),
        *(
            ("data", "memories", entry.index, field)
            for entry in sheet.memory_entries
            for field in ("title", "summary", "location", "intent", "outcome", "tags")
        ),
    }
    if not set(draft._edits).issubset(supported_paths):
        raise CharacterSheetRenderError("this draft contains unsupported v2 edits")
    json_bytes = sheet.raw_html[
        sheet.script_span.content_start : sheet.script_span.content_end
    ]
    replacements: list[tuple[int, int, bytes]] = []
    memory_edits: dict[int, dict[str, str | list[str]]] = {}
    for path, value in draft._edits.items():
        if len(path) == 4 and path[1] == "memories":
            index = path[2]
            field_name = path[3]
            if not isinstance(index, int) or not isinstance(field_name, str):
                raise CharacterSheetRenderError("memory edit path is invalid")
            if field_name == "tags":
                if not isinstance(value, list) or not all(
                    isinstance(tag, str) for tag in value
                ):
                    raise CharacterSheetRenderError("memory tags must be strings")
            elif not isinstance(value, str):
                raise CharacterSheetRenderError("memory text values must be strings")
            memory_edits.setdefault(index, {})[field_name] = value
    baseline_memory_order = tuple(range(len(sheet.memory_entries)))
    memory_order_changed = draft._memory_order != baseline_memory_order

    for path, value in draft._edits.items():
        if len(path) == 4 and path[1] == "memories":
            continue
        if not isinstance(value, str):
            raise CharacterSheetRenderError("text draft values must be strings")
        if path == ("data", "name"):
            section = sheet.diagnostic_baseline.for_section("name")
            if not section.editable or sheet.name_span is None:
                raise CharacterSheetRenderError("name section is read-only")
            json_span = _data_field_span(json_bytes, "name")
            html_span = sheet.name_span
            display_value = value if value else "（未入力）"
        elif path[1] == "profile":
            section = sheet.diagnostic_baseline.for_section("profile")
            if not section.editable:
                raise CharacterSheetRenderError("profile section is read-only")
            key = path[2]
            json_span = _nested_data_field_span(json_bytes, "profile", key)
            html_span = dict(sheet.profile_spans).get(key)
            display_value = value if value else "（未入力）"
        elif path[1] == "status":
            section = sheet.diagnostic_baseline.for_section("status")
            if not section.editable:
                raise CharacterSheetRenderError("status section is read-only")
            key = path[2]
            entry = dict(sheet.status_entries).get(key)
            json_span = _nested_data_field_span(json_bytes, "status", key)
            if json_span is None or entry is None:
                raise CharacterSheetRenderError(f"could not locate the {key} status")
            replacements.append(
                (
                    sheet.script_span.content_start + json_span.start,
                    sheet.script_span.content_start + json_span.end,
                    dumps_script_safe_string(value),
                )
            )
            replacements.append(
                (
                    entry.rank_span.content_start,
                    entry.rank_span.content_end,
                    value.encode("ascii"),
                )
            )
            active_count = STATUS_RANKS[value]
            for index, gauge_li in enumerate(entry.gauge_lis):
                replacement = (
                    b'<li class="active"></li>' if index < active_count else b"<li></li>"
                )
                replacements.append((gauge_li.start, gauge_li.end, replacement))
            continue
        if json_span is None or html_span is None:
            raise CharacterSheetRenderError(f"could not locate the {path[-1]} field")
        replacements.extend(
            (
                (
                    sheet.script_span.content_start + json_span.start,
                    sheet.script_span.content_start + json_span.end,
                    dumps_script_safe_string(value),
                ),
                (
                    html_span.content_start,
                    html_span.content_end,
                    html.escape(display_value, quote=False).encode("utf-8"),
                ),
            )
        )

    if draft._icon_replacement is not None:
        section = sheet.diagnostic_baseline.for_section("icon")
        if not section.editable or sheet.icon_span is None:
            raise CharacterSheetRenderError("icon section is read-only")
        icon_span = _data_field_span(json_bytes, "icon")
        if icon_span is None:
            raise CharacterSheetRenderError("icon JSON object is unavailable")
        icon_bytes = json_bytes[icon_span.start : icon_span.end]
        mime, data_uri = draft._icon_replacement
        try:
            patched_icon = replace_value_fields_in_object(
                icon_bytes,
                {
                    "mime": dumps_script_safe_string(mime),
                    "dataUri": dumps_script_safe_string(data_uri),
                },
            )
        except JsonPatchError as exc:
            raise CharacterSheetRenderError(str(exc)) from exc
        replacements.extend(
            (
                (
                    sheet.script_span.content_start + icon_span.start,
                    sheet.script_span.content_start + icon_span.end,
                    patched_icon,
                ),
                (
                    sheet.icon_span.start,
                    sheet.icon_span.end,
                    build_patched_start_tag_attr(
                        sheet.raw_html,
                        sheet.icon_span,
                        attr_name="src",
                        value=data_uri,
                    ),
                ),
            )
        )

    patched_memory_objects: dict[int, bytes] = {}
    patched_memory_lis: dict[int, bytes] = {}
    patched_memory_values: dict[int, dict[str, Any]] = {}
    if draft._memory_replacements:
        section = sheet.diagnostic_baseline.for_section("memories")
        if not section.editable:
            raise CharacterSheetRenderError("memory section is read-only")
        spans = locate_data_object_array(json_bytes, "memories")
        entries_by_index = {entry.index: entry for entry in sheet.memory_entries}
        for index, replacement_memory in draft._memory_replacements.items():
            entry = entries_by_index.get(index)
            if entry is None or index >= len(spans.objects):
                raise CharacterSheetRenderError("memory replacement target is unavailable")
            object_span = spans.objects[index]
            encoded_object = dumps_script_safe(replacement_memory, indent=8)
            patched_memory_objects[index] = encoded_object
            patched_memory_values[index] = replacement_memory
            rendered_li = build_new_memory_li(replacement_memory)
            if entry.html_li is not None:
                patched_memory_lis[index] = rendered_li
            if not memory_order_changed:
                replacements.append(
                    (
                        sheet.script_span.content_start + object_span.start,
                        sheet.script_span.content_start + object_span.end,
                        encoded_object,
                    )
                )
                if entry.html_li is not None:
                    replacements.append(
                        (entry.html_li.start, entry.html_li.end, rendered_li)
                    )
    if memory_edits:
        section = sheet.diagnostic_baseline.for_section("memories")
        if not section.editable:
            raise CharacterSheetRenderError("memory section is read-only")
        spans = locate_data_object_array(json_bytes, "memories")
        entries_by_index = {entry.index: entry for entry in sheet.memory_entries}
        for index, edits in memory_edits.items():
            entry = entries_by_index.get(index)
            if entry is None or entry.is_placeholder or index >= len(spans.objects):
                raise CharacterSheetRenderError("memory is unavailable for editing")
            object_span = spans.objects[index]
            object_bytes = json_bytes[object_span.start : object_span.end]
            encoded_fields = {
                field_name: (
                    dumps_script_safe(value)
                    if field_name == "tags"
                    else dumps_script_safe_string(value)
                )
                for field_name, value in edits.items()
            }
            try:
                patched_object = replace_value_fields_in_object(
                    object_bytes,
                    encoded_fields,
                )
            except JsonPatchError as exc:
                raise CharacterSheetRenderError(str(exc)) from exc
            patched_memory_objects[index] = patched_object
            patched_value = dict(entry.memory)
            patched_value.update(edits)
            patched_memory_values[index] = patched_value
            if entry.html_li is not None:
                patched_memory_lis[index] = build_patched_memory_li_fields(
                    sheet.raw_html,
                    entry.html_li,
                    replacements=edits,
                )
            if not memory_order_changed:
                replacements.append(
                    (
                        sheet.script_span.content_start + object_span.start,
                        sheet.script_span.content_start + object_span.end,
                        patched_object,
                    )
                )
                if index in patched_memory_lis:
                    replacements.append(
                        (
                            entry.html_li.start,
                            entry.html_li.end,
                            patched_memory_lis[index],
                        )
                    )

    if memory_order_changed:
        section = sheet.diagnostic_baseline.for_section("memories")
        if not section.editable:
            raise CharacterSheetRenderError("memory section is read-only")
        valid_sources = set(baseline_memory_order) | set(draft._new_memories)
        if (
            len(set(draft._memory_order)) != len(draft._memory_order)
            or any(index not in valid_sources for index in draft._memory_order)
        ):
            raise CharacterSheetRenderError("memory order contains an invalid source")
        spans = locate_data_object_array(json_bytes, "memories")
        if len(spans.objects) != len(baseline_memory_order):
            raise CharacterSheetRenderError("baseline memory object count changed")
        new_memory_objects = {
            token: dumps_script_safe(memory, indent=8)
            for token, memory in draft._new_memories.items()
        }
        replacements.append(
            (
                sheet.script_span.content_start + spans.array.start,
                sheet.script_span.content_start + spans.array.end,
                _reordered_object_array_bytes(
                    json_bytes,
                    spans.array,
                    spans.objects,
                    draft._memory_order,
                    object_overrides=patched_memory_objects,
                    extra_objects=new_memory_objects,
                ),
            )
        )
        memories_ul = find_unique_memories_ul(sheet.raw_html)
        visual_lis = find_direct_lis(sheet.raw_html, memories_ul)
        if len(visual_lis) != 6:
            raise CharacterSheetRenderError("memory HTML no longer has six slots")
        entries_by_index = {entry.index: entry for entry in sheet.memory_entries}
        for position, visual_li in enumerate(visual_lis):
            if position >= len(draft._memory_order):
                rendered_li = b"<li>&nbsp;</li>"
            else:
                source_index = draft._memory_order[position]
                source_entry = entries_by_index.get(source_index)
                if source_index in draft._new_memories:
                    rendered_li = build_new_memory_li(
                        draft._new_memories[source_index]
                    )
                elif source_index in patched_memory_lis:
                    rendered_li = patched_memory_lis[source_index]
                elif source_entry is not None and source_entry.html_li is not None:
                    rendered_li = source_entry.html_li.raw
                else:
                    if source_entry is None:
                        raise CharacterSheetRenderError(
                            "memory order references an unavailable source"
                        )
                    rendered_li = build_new_memory_li(
                        patched_memory_values.get(source_index, source_entry.memory)
                    )
            replacements.append((visual_li.start, visual_li.end, rendered_li))
    updated = sheet.raw_html
    for start, end, replacement in sorted(replacements, reverse=True):
        updated = updated[:start] + replacement + updated[end:]
    return updated


def validate_rendered_character_sheet(
    baseline: CharacterSheet,
    rendered: bytes,
) -> CharacterSheet:
    """Validate one save against immutable load-time section diagnostics."""

    if baseline.whole_sheet_read_only:
        raise CharacterSheetRenderError(
            "unknown formatVersion sheets cannot be conversion-saved"
        )
    candidate = load_character_sheet(rendered)
    if candidate.whole_sheet_read_only:
        raise CharacterSheetRenderError(
            "rendered sheet changed to an unknown formatVersion"
        )
    if candidate.format_version != baseline.format_version:
        raise CharacterSheetRenderError("formatVersion changed during rendering")

    for baseline_section in baseline.diagnostic_baseline.sections:
        try:
            candidate_section = candidate.diagnostic_baseline.for_section(
                baseline_section.name
            )
        except KeyError as exc:
            raise CharacterSheetRenderError(
                f"rendered sheet lost the {baseline_section.name} section diagnostic"
            ) from exc
        if baseline_section.editable:
            if not candidate_section.editable:
                raise CharacterSheetRenderError(
                    f"rendered {baseline_section.name} section failed validation"
                )
            continue
        if (
            candidate_section.json_bytes != baseline_section.json_bytes
            or candidate_section.html_bytes != baseline_section.html_bytes
        ):
            raise CharacterSheetRenderError(
                f"read-only {baseline_section.name} section bytes changed"
            )
        baseline_facts = (
            baseline_section.diagnostic_codes,
            baseline_section.severity,
            baseline_section.json_count,
            baseline_section.html_count,
            baseline_section.position_consistent,
            baseline_section.read_only_reason,
        )
        candidate_facts = (
            candidate_section.diagnostic_codes,
            candidate_section.severity,
            candidate_section.json_count,
            candidate_section.html_count,
            candidate_section.position_consistent,
            candidate_section.read_only_reason,
        )
        if candidate_facts != baseline_facts:
            raise CharacterSheetRenderError(
                f"read-only {baseline_section.name} diagnostics changed"
            )
    return candidate


def create_character_sheet(*, icon_webp: bytes, generation: GenerationInputs) -> bytes:
    """Create a new sheet from the Phase 0 validated golden contract."""

    document = build_candidate_golden_document(
        icon_webp=icon_webp,
        generation=generation,
    )
    return render_candidate_html(document)


def load_character_sheet(raw_html: bytes) -> CharacterSheet:
    try:
        script_span = find_unique_script_json(raw_html)
        ul_span = find_unique_skills_ul(raw_html)
    except HtmlStructureError as exc:
        raise CharacterSheetError(str(exc)) from exc

    try:
        parsed = json.loads(raw_html[script_span.content_start : script_span.content_end].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CharacterSheetError(f"failed to parse character-sheet-data JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise CharacterSheetError("character-sheet-data JSON root is not an object")
    data = parsed.get("data")
    if not isinstance(data, dict):
        raise CharacterSheetError("character-sheet-data.data is not an object")
    skills = data.get("skills")
    if not isinstance(skills, list) or not all(isinstance(skill, dict) for skill in skills):
        raise CharacterSheetError("character-sheet-data.data.skills is not a list of objects")

    personalities = data.get("personalities")
    if not isinstance(personalities, list) or not all(isinstance(item, dict) for item in personalities):
        personalities = []
        personality_data_error = "character-sheet-data.data.personalities is not a list of objects"
    else:
        personality_data_error = ""

    lis = find_direct_skill_lis(raw_html, ul_span)
    trailing_lis = lis[len(skills) :] if len(lis) >= len(skills) else []
    trailing_slots_are_vacant = all(_is_vacant_html_slot(li) for li in trailing_lis)
    counts_are_compatible = len(lis) >= len(skills) and trailing_slots_are_vacant
    read_only = not counts_are_compatible
    reason = ""
    if read_only:
        reason = f"skill count mismatch: JSON has {len(skills)}, HTML has {len(lis)} direct li elements"
        if len(lis) > len(skills):
            reason += "; trailing HTML entries are not safe vacant slots"

    duplicate_ids = duplicate_string_ids(skills)
    entries: list[SkillEntry] = []
    for index, skill in enumerate(skills):
        if index < len(lis):
            li = lis[index]
            position_consistent = (not read_only) and _position_consistent(skill, li)
        else:
            li = _missing_li()
            position_consistent = False
        classification = classify_skill(
            skill,
            position_consistent=position_consistent,
            duplicate_ids=duplicate_ids,
        )
        entries.append(
            SkillEntry(
                index=index,
                skill=skill,
                li=li,
                position_consistent=position_consistent,
                classification=classification,
            )
        )

    if any(not entry.position_consistent for entry in entries):
        read_only = True
        if not reason:
            reason = "JSON and HTML skill entries do not safely match by position"

    (
        personality_ul_span,
        personality_entries,
        personality_lis,
        personality_slot_count,
        personality_read_only,
        personality_reason,
    ) = _load_personalities(raw_html, personalities, personality_data_error)

    try:
        name_span = find_unique_element_by_id(raw_html, "name-value")
    except HtmlStructureError:
        name_span = None
    name_value = data.get("name")
    name_position_consistent = bool(
        isinstance(name_value, str)
        and name_span is not None
        and _plain_html_text(raw_html[name_span.content_start : name_span.content_end])
        == (name_value if name_value else "（未入力）")
    )
    (
        profile_spans,
        profile_html_raw,
        profile_position_consistent,
        profile_reason,
    ) = _load_profile_html(raw_html, data.get("profile"))
    (
        status_entries,
        status_html_raw,
        status_position_consistent,
        status_reason,
    ) = _load_status_html(raw_html, data.get("status"))
    (
        memory_entries,
        memory_html_raw,
        memory_html_count,
        memory_position_consistent,
        memory_reason,
    ) = _load_memories(raw_html, data.get("memories"))
    (
        icon_span,
        icon_html_raw,
        icon_position_consistent,
        icon_reason,
    ) = _load_icon_html(raw_html, data.get("icon"))

    format_version = parsed.get("formatVersion")
    whole_sheet_read_only = (
        "formatVersion" in parsed and format_version != "1.0.0"
    )
    if whole_sheet_read_only:
        read_only = True
        reason = "unknown or unsupported formatVersion"
        personality_read_only = True
        personality_reason = reason

    json_bytes = raw_html[script_span.content_start : script_span.content_end]
    diagnostic_baseline = _build_diagnostic_baseline(
        json_bytes=json_bytes,
        data=data,
        skills_ul_raw=raw_html[ul_span.start : ul_span.end],
        personality_ul_raw=(
            raw_html[personality_ul_span.start : personality_ul_span.end]
            if personality_ul_span is not None
            else b""
        ),
        skill_json_count=len(skills),
        skill_html_count=len(lis),
        skill_read_only=read_only,
        skill_reason=reason,
        personality_json_count=len(personalities),
        personality_html_count=personality_slot_count,
        personality_read_only=personality_read_only,
        personality_reason=personality_reason,
        whole_sheet_read_only=whole_sheet_read_only,
        name_html_raw=(
            raw_html[name_span.start : name_span.end] if name_span is not None else b""
        ),
        name_position_consistent=name_position_consistent,
        profile_html_raw=profile_html_raw,
        profile_position_consistent=profile_position_consistent,
        profile_reason=profile_reason,
        status_html_raw=status_html_raw,
        status_position_consistent=status_position_consistent,
        status_reason=status_reason,
        memory_html_raw=memory_html_raw,
        memory_html_count=memory_html_count,
        memory_position_consistent=memory_position_consistent,
        memory_reason=memory_reason,
        icon_html_raw=icon_html_raw,
        icon_position_consistent=icon_position_consistent,
        icon_reason=icon_reason,
    )

    return CharacterSheet(
        raw_html=raw_html,
        data=parsed,
        script_span=script_span,
        skills_ul_span=ul_span,
        entries=entries,
        vacant_lis=trailing_lis if counts_are_compatible else [],
        slot_count=len(lis),
        vacant_slot_count=len(trailing_lis) if counts_are_compatible else 0,
        read_only=read_only,
        read_only_reason=reason,
        personality_ul_span=personality_ul_span,
        personality_entries=personality_entries,
        personality_lis=personality_lis,
        personality_slot_count=personality_slot_count,
        personality_read_only=personality_read_only,
        personality_read_only_reason=personality_reason,
        format_version=format_version,
        whole_sheet_read_only=whole_sheet_read_only,
        diagnostic_baseline=diagnostic_baseline,
        name_span=name_span,
        profile_spans=profile_spans,
        status_entries=status_entries,
        memory_entries=memory_entries,
        icon_span=icon_span,
    )


def _build_diagnostic_baseline(
    *,
    json_bytes: bytes,
    data: dict[str, Any],
    skills_ul_raw: bytes,
    personality_ul_raw: bytes,
    skill_json_count: int,
    skill_html_count: int,
    skill_read_only: bool,
    skill_reason: str,
    personality_json_count: int,
    personality_html_count: int,
    personality_read_only: bool,
    personality_reason: str,
    whole_sheet_read_only: bool,
    name_html_raw: bytes,
    name_position_consistent: bool,
    profile_html_raw: bytes,
    profile_position_consistent: bool,
    profile_reason: str,
    status_html_raw: bytes,
    status_position_consistent: bool,
    status_reason: str,
    memory_html_raw: bytes,
    memory_html_count: int,
    memory_position_consistent: bool,
    memory_reason: str,
    icon_html_raw: bytes,
    icon_position_consistent: bool,
    icon_reason: str,
) -> DiagnosticBaseline:
    unknown_codes = ("unknown-format-version",) if whole_sheet_read_only else ()
    sections: list[SectionDiagnosticBaseline] = []
    for name in ("name", "profile", "status", "icon"):
        value = data.get(name)
        expected_type = str if name == "name" else dict
        valid = isinstance(value, expected_type)
        if name == "profile":
            valid = valid and all(
                isinstance(value.get(key), str) for key, _tab in PROFILE_TABS
            )
        if name == "status":
            valid = valid and all(
                isinstance(value.get(key), str) and value.get(key) in STATUS_RANKS
                for key, _label in STATUS_HTML_FIELDS
            )
            valid = valid and isinstance(value.get("charm"), str)
        if name == "icon":
            valid = valid and isinstance(value.get("mime"), str)
            valid = valid and isinstance(value.get("dataUri"), str)
        position_valid = (
            name_position_consistent
            if name == "name"
            else (
                profile_position_consistent
                if name == "profile"
                else (
                    status_position_consistent
                    if name == "status"
                    else icon_position_consistent if name == "icon" else True
                )
            )
        )
        codes = unknown_codes or (
            ()
            if valid and position_valid
            else (("json-html-mismatch",) if valid else ("invalid-json-section",))
        )
        sections.append(
            SectionDiagnosticBaseline(
                name=name,
                editable=not whole_sheet_read_only and valid and position_valid,
                diagnostic_codes=codes,
                severity="error" if codes else "none",
                position_consistent=(
                    name_position_consistent
                    if name == "name"
                    else (
                        profile_position_consistent
                        if name == "profile"
                        else (
                            status_position_consistent
                            if name == "status"
                            else icon_position_consistent if name == "icon" else None
                        )
                    )
                ),
                json_bytes=_data_field_bytes(json_bytes, name),
                html_bytes=(
                    name_html_raw
                    if name == "name"
                    else (
                        profile_html_raw
                        if name == "profile"
                        else (
                            status_html_raw
                            if name == "status"
                            else icon_html_raw if name == "icon" else b""
                        )
                    )
                ),
                read_only_reason=(
                    "unknown or unsupported formatVersion"
                    if whole_sheet_read_only
                    else (
                        ""
                        if valid and position_valid
                        else (
                            f"data.{name} has an unsupported type"
                            if not valid
                            else (
                                profile_reason
                                if name == "profile"
                                else (
                                    status_reason
                                    if name == "status"
                                    else (
                                        icon_reason
                                        if name == "icon"
                                        else "JSON and HTML name values do not match"
                                    )
                                )
                            )
                        )
                    )
                ),
            )
        )

    sections.append(
        SectionDiagnosticBaseline(
            name="skills",
            editable=not whole_sheet_read_only and not skill_read_only,
            diagnostic_codes=unknown_codes
            or (("json-html-mismatch",) if skill_read_only else ()),
            severity="error" if whole_sheet_read_only or skill_read_only else "none",
            json_count=skill_json_count,
            html_count=skill_html_count,
            position_consistent=not skill_read_only,
            json_bytes=_data_field_bytes(json_bytes, "skills"),
            html_bytes=skills_ul_raw,
            read_only_reason=(
                "unknown or unsupported formatVersion"
                if whole_sheet_read_only
                else skill_reason
            ),
        )
    )
    sections.append(
        SectionDiagnosticBaseline(
            name="personalities",
            editable=not whole_sheet_read_only and not personality_read_only,
            diagnostic_codes=unknown_codes
            or (("json-html-mismatch",) if personality_read_only else ()),
            severity="error" if whole_sheet_read_only or personality_read_only else "none",
            json_count=personality_json_count,
            html_count=personality_html_count,
            position_consistent=not personality_read_only,
            json_bytes=_data_field_bytes(json_bytes, "personalities"),
            html_bytes=personality_ul_raw,
            read_only_reason=(
                "unknown or unsupported formatVersion"
                if whole_sheet_read_only
                else personality_reason
            ),
        )
    )

    memories = data.get("memories")
    memories_valid = isinstance(memories, list) and all(
        isinstance(memory, dict) for memory in memories
    )
    memory_codes = unknown_codes or (() if memories_valid else ("invalid-json-section",))
    if not whole_sheet_read_only and memories_valid and not memory_position_consistent:
        memory_codes = ("json-html-mismatch",)
    sections.append(
        SectionDiagnosticBaseline(
            name="memories",
            editable=(
                not whole_sheet_read_only
                and memories_valid
                and memory_position_consistent
            ),
            diagnostic_codes=memory_codes,
            severity="error" if memory_codes else "none",
            json_count=len(memories) if isinstance(memories, list) else None,
            html_count=memory_html_count,
            position_consistent=memory_position_consistent,
            json_bytes=_data_field_bytes(json_bytes, "memories"),
            html_bytes=memory_html_raw,
            read_only_reason=(
                "unknown or unsupported formatVersion"
                if whole_sheet_read_only
                else (
                    ""
                    if memories_valid and memory_position_consistent
                    else (
                        memory_reason
                        if memories_valid
                        else "data.memories has an unsupported type"
                    )
                )
            ),
        )
    )
    return DiagnosticBaseline(tuple(sections))


def _data_field_bytes(json_bytes: bytes, key: str) -> bytes:
    span = _data_field_span(json_bytes, key)
    return json_bytes[span.start : span.end] if span is not None else b""


def _data_field_span(json_bytes: bytes, key: str) -> JsonValueSpan | None:
    try:
        data_span = find_object_key_value(json_bytes, "data", expected_start=b"{")
        data_bytes = json_bytes[data_span.start : data_span.end]
        field_span = find_object_key_value(data_bytes, key)
    except JsonSpanError:
        return None
    return JsonValueSpan(
        data_span.start + field_span.start,
        data_span.start + field_span.end,
    )


def _nested_data_field_span(
    json_bytes: bytes,
    object_key: str,
    field_key: str,
) -> JsonValueSpan | None:
    object_span = _data_field_span(json_bytes, object_key)
    if object_span is None:
        return None
    object_bytes = json_bytes[object_span.start : object_span.end]
    try:
        field_span = find_object_key_value(object_bytes, field_key)
    except JsonSpanError:
        return None
    return JsonValueSpan(
        object_span.start + field_span.start,
        object_span.start + field_span.end,
    )


def _reordered_object_array_bytes(
    json_bytes: bytes,
    array_span: JsonValueSpan,
    object_spans: list[JsonValueSpan],
    order: tuple[int, ...],
    *,
    object_overrides: dict[int, bytes] | None = None,
    extra_objects: dict[int, bytes] | None = None,
) -> bytes:
    if object_spans:
        prefix = json_bytes[array_span.start : object_spans[0].start]
        suffix = json_bytes[object_spans[-1].end : array_span.end]
    else:
        prefix = json_bytes[array_span.start : array_span.end - 1]
        suffix = json_bytes[array_span.end - 1 : array_span.end]
    separators = [
        json_bytes[object_spans[index].end : object_spans[index + 1].start]
        for index in range(len(object_spans) - 1)
    ]
    overrides = object_overrides or {}
    objects = [
        overrides.get(index, json_bytes[span.start : span.end])
        for index, span in enumerate(object_spans)
    ]
    source_objects = {index: value for index, value in enumerate(objects)}
    source_objects.update(extra_objects or {})
    chunks = [prefix]
    for position, source_index in enumerate(order):
        if position:
            if position - 1 < len(separators):
                chunks.append(separators[position - 1])
            elif separators:
                chunks.append(separators[-1])
            else:
                chunks.append(b", ")
        chunks.append(source_objects[source_index])
    chunks.append(suffix)
    return b"".join(chunks)


def _plain_html_text(raw: bytes) -> str | None:
    if b"<" in raw or b">" in raw:
        return None
    try:
        return html.unescape(raw.decode("utf-8"))
    except UnicodeDecodeError:
        return None


def _load_profile_html(
    raw_html: bytes,
    profile: object,
) -> tuple[tuple[tuple[str, ElementSpan], ...], bytes, bool, str]:
    if not isinstance(profile, dict):
        return (), b"", False, "data.profile has an unsupported type"
    try:
        detail_span = find_unique_element_by_id(raw_html, "detail")
    except HtmlStructureError as exc:
        return (), b"", False, str(exc)

    spans: list[tuple[str, ElementSpan]] = []
    for key, tab in PROFILE_TABS:
        value = profile.get(key)
        if not isinstance(value, str):
            return tuple(spans), raw_html[detail_span.start : detail_span.end], False, (
                f"data.profile.{key} is not a string"
            )
        try:
            span = find_unique_descendant_by_attrs(
                raw_html,
                detail_span,
                tag_name="div",
                required_attrs={"class": "tab-content", "data-tab-key": tab},
            )
        except HtmlStructureError as exc:
            return tuple(spans), raw_html[detail_span.start : detail_span.end], False, str(exc)
        displayed = _plain_html_text(raw_html[span.content_start : span.content_end])
        if displayed != value and not (value == "" and displayed in ("", "（未入力）")):
            return tuple(spans), raw_html[detail_span.start : detail_span.end], False, (
                f"JSON and HTML profile values do not match for {key}"
            )
        spans.append((key, span))
    return (
        tuple(spans),
        raw_html[detail_span.start : detail_span.end],
        True,
        "",
    )


def _load_status_html(
    raw_html: bytes,
    status: object,
) -> tuple[tuple[tuple[str, StatusEntry], ...], bytes, bool, str]:
    if not isinstance(status, dict):
        return (), b"", False, "data.status has an unsupported type"
    if not isinstance(status.get("charm"), str):
        return (), b"", False, "data.status.charm is not a string"
    try:
        abilities_span = find_unique_abilities_ul(raw_html)
        rows = find_direct_lis(raw_html, abilities_span)
    except HtmlStructureError as exc:
        return (), b"", False, str(exc)
    html_raw = raw_html[abilities_span.start : abilities_span.end]
    if len(rows) != len(STATUS_HTML_FIELDS):
        return (), html_raw, False, (
            f"status count mismatch: expected {len(STATUS_HTML_FIELDS)}, found {len(rows)}"
        )

    entries: list[tuple[str, StatusEntry]] = []
    for index, (key, label) in enumerate(STATUS_HTML_FIELDS):
        rank = status.get(key)
        if not isinstance(rank, str) or rank not in STATUS_RANKS:
            return tuple(entries), html_raw, False, f"data.status.{key} has an invalid rank"
        row = rows[index]
        row_span = _element_span_from_li(row)
        try:
            label_span = find_unique_descendant_by_attrs(
                raw_html,
                row_span,
                tag_name="span",
                required_attrs={"class": "ability-label", "data-i18n-key": label},
            )
            gauge_span = find_unique_descendant_by_attrs(
                raw_html,
                row_span,
                tag_name="ul",
                required_attrs={"class": "parameter-block"},
            )
            rank_span = find_unique_descendant_by_attrs(
                raw_html,
                row_span,
                tag_name="span",
                required_attrs={"class": "parameter-rank"},
            )
            gauge_lis = tuple(find_direct_lis(raw_html, gauge_span))
        except HtmlStructureError as exc:
            return tuple(entries), html_raw, False, str(exc)
        if _plain_html_text(
            raw_html[label_span.content_start : label_span.content_end]
        ) is None:
            return tuple(entries), html_raw, False, f"status label {label} is not plain text"
        if len(gauge_lis) != 6:
            return tuple(entries), html_raw, False, (
                f"status {key} gauge has {len(gauge_lis)} segments instead of 6"
            )
        displayed_rank = _plain_html_text(
            raw_html[rank_span.content_start : rank_span.content_end]
        )
        if displayed_rank != rank:
            return tuple(entries), html_raw, False, (
                f"JSON and HTML status ranks do not match for {key}"
            )
        expected_active = STATUS_RANKS[rank]
        active_flags = [
            "active" in gauge.attrs.get("class", "").split() for gauge in gauge_lis
        ]
        if active_flags != [position < expected_active for position in range(6)]:
            return tuple(entries), html_raw, False, (
                f"status gauge does not match rank for {key}"
            )
        entries.append(
            (
                key,
                StatusEntry(
                    key=key,
                    rank=rank,
                    li=row,
                    rank_span=rank_span,
                    gauge_lis=gauge_lis,
                ),
            )
        )
    return tuple(entries), html_raw, True, ""


def _element_span_from_li(li: LiSpan) -> ElementSpan:
    return ElementSpan(
        start=li.start,
        end=li.end,
        start_tag_start=li.start_tag_start,
        start_tag_end=li.start_tag_end,
        content_start=li.content_start,
        content_end=li.content_end,
        end_tag_start=li.content_end,
        end_tag_end=li.end,
    )


def _load_memories(
    raw_html: bytes,
    memories: object,
) -> tuple[tuple[MemoryEntry, ...], bytes, int, bool, str]:
    if not isinstance(memories, list) or not all(
        isinstance(memory, dict) for memory in memories
    ):
        return (), b"", 0, False, "data.memories is not a list of objects"
    try:
        memories_span = find_unique_memories_ul(raw_html)
        lis = find_direct_lis(raw_html, memories_span)
    except HtmlStructureError as exc:
        return (), b"", 0, False, str(exc)
    html_raw = raw_html[memories_span.start : memories_span.end]
    if len(lis) != 6:
        return (), html_raw, len(lis), False, (
            f"memory slot count mismatch: expected 6, found {len(lis)}"
        )

    entries: list[MemoryEntry] = []
    for index, memory in enumerate(memories):
        valid, placeholder, reason = _validate_memory_object(memory)
        if not valid:
            return tuple(entries), html_raw, len(lis), False, (
                f"memory {index + 1}: {reason}"
            )
        li = lis[index] if index < 6 else None
        if li is not None:
            if placeholder:
                if not _is_vacant_html_slot(li):
                    return tuple(entries), html_raw, len(lis), False, (
                        f"placeholder memory {index + 1} has non-empty HTML"
                    )
            elif not _memory_matches_li(memory, li):
                return tuple(entries), html_raw, len(lis), False, (
                    f"JSON and HTML memories do not match at position {index + 1}"
                )
        entries.append(
            MemoryEntry(
                index=index,
                memory=memory,
                is_placeholder=placeholder,
                html_li=li,
            )
        )

    for index, li in enumerate(lis[len(memories) :], start=len(memories)):
        if not _is_vacant_html_slot(li):
            return tuple(entries), html_raw, len(lis), False, (
                f"memory slot {index + 1} is not a safe empty slot"
            )
    return tuple(entries), html_raw, len(lis), True, ""


def _validate_memory_object(memory: dict[str, Any]) -> tuple[bool, bool, str]:
    string_keys = ("id", "title", "summary", "location", "intent", "outcome")
    if any(not isinstance(memory.get(key), str) for key in string_keys):
        return False, False, "known text fields must be strings"
    tags = memory.get("tags")
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        return False, False, "tags must be an array of strings"
    placeholder = memory.get("isPlaceholder")
    if not isinstance(placeholder, bool):
        return False, False, "isPlaceholder must be a boolean"
    if placeholder and (
        any(memory.get(key) != "" for key in string_keys) or tags != []
    ):
        return False, True, "placeholder fields must use the complete empty structure"
    return True, placeholder, ""


def _memory_matches_li(memory: dict[str, Any], li: LiSpan) -> bool:
    checks = {
        "id": "data-memory-id",
        "title": "data-memory-title",
        "summary": "data-memory-summary",
        "location": "data-memory-location",
        "intent": "data-memory-intent",
        "outcome": "data-memory-outcome",
    }
    if any(li.attrs.get(attr) != memory.get(key) for key, attr in checks.items()):
        return False
    tags_raw = li.attrs.get("data-memory-tags")
    if tags_raw is None:
        return False
    try:
        tags = json.loads(tags_raw)
    except json.JSONDecodeError:
        return False
    return tags == memory.get("tags") and text_content(li.inner) == memory.get("title")


def _load_icon_html(
    raw_html: bytes,
    icon: object,
) -> tuple[StartTagSpan | None, bytes, bool, str]:
    if not isinstance(icon, dict):
        return None, b"", False, "data.icon has an unsupported type"
    mime = icon.get("mime")
    data_uri = icon.get("dataUri")
    if not isinstance(mime, str) or not isinstance(data_uri, str):
        return None, b"", False, "data.icon mime and dataUri must be strings"
    try:
        span = find_unique_start_tag_by_id(
            raw_html,
            "icon-value",
            tag_name="img",
        )
    except HtmlStructureError as exc:
        return None, b"", False, str(exc)
    if span.attrs.get("src") != data_uri:
        return span, span.raw, False, "JSON and HTML icon data URIs do not match"
    return span, span.raw, True, ""


def _load_personalities(
    raw_html: bytes,
    personalities: list[dict[str, Any]],
    data_error: str,
) -> tuple[ElementSpan | None, tuple[PersonalityEntry, ...], tuple[LiSpan, ...], int, bool, str]:
    if data_error:
        return None, (), (), 0, True, data_error
    try:
        ul_span = find_unique_personality_ul(raw_html)
        lis = find_direct_personality_lis(raw_html, ul_span)
    except HtmlStructureError as exc:
        return None, (), (), 0, True, str(exc)

    if len(lis) != 6:
        return ul_span, (), tuple(lis), len(lis), True, (
            f"personality slot count mismatch: expected 6 direct li elements, found {len(lis)}"
        )
    if len(personalities) > len(lis):
        return ul_span, (), tuple(lis), len(lis), True, (
            f"personality count mismatch: JSON has {len(personalities)}, HTML has {len(lis)} direct li elements"
        )

    try:
        catalog = catalog_by_id(load_personality_catalog())
    except PersonalityCatalogError as exc:
        return ul_span, (), tuple(lis), len(lis), True, str(exc)
    entries: list[PersonalityEntry] = []
    seen_ids: set[int] = set()
    for index, keyword in enumerate(personalities):
        keyword_id = keyword.get("id")
        catalog_keyword = catalog.get(keyword_id) if isinstance(keyword_id, int) and not isinstance(keyword_id, bool) else None
        if catalog_keyword is None or keyword != catalog_keyword.as_dict():
            return ul_span, tuple(entries), tuple(lis), len(lis), True, (
                f"personality {index + 1} does not exactly match the bundled catalog"
            )
        if keyword_id in seen_ids:
            return ul_span, tuple(entries), tuple(lis), len(lis), True, (
                f"personality {index + 1} duplicates an earlier keyword"
            )
        seen_ids.add(keyword_id)
        li = lis[index]
        if li.attrs or text_content(li.inner) != catalog_keyword.name:
            return ul_span, tuple(entries), tuple(lis), len(lis), True, (
                f"JSON and HTML personality entries do not safely match at position {index + 1}"
            )
        entries.append(PersonalityEntry(index=index, keyword=keyword, li=li))

    for index, li in enumerate(lis[len(personalities) :], start=len(personalities)):
        if li.attrs or b"<" in li.inner or text_content(li.inner) != "":
            return ul_span, tuple(entries), tuple(lis), len(lis), True, (
                f"personality slot {index + 1} is not a safe empty slot"
            )
    return ul_span, tuple(entries), tuple(lis), len(lis), False, ""


def _position_consistent(skill: dict[str, Any], li: LiSpan) -> bool:
    if _json_empty_slot(skill):
        return li.attrs == {} and text_content(li.inner) in ("", "\xa0")

    checks = {
        "id": "data-skill-id",
        "name": "data-skill-name",
        "type": "data-skill-type",
        "description": "data-skill-description",
    }
    for json_key, attr_name in checks.items():
        json_value = skill.get(json_key, "")
        if json_value is None:
            json_value = ""
        if not isinstance(json_value, str):
            json_value = str(json_value)
        if li.attrs.get(attr_name, "") != json_value:
            return False
    return text_content(li.inner) == skill.get("name", "")


def _json_empty_slot(skill: dict[str, Any]) -> bool:
    return (
        skill.get("id") in ("", None)
        and skill.get("name") in ("", None)
        and skill.get("description") in ("", None)
        and skill.get("type") in ("", None)
        and skill.get("key") in ("", None)
    )


def _is_vacant_html_slot(li: LiSpan) -> bool:
    """Recognize an unassigned visual slot that has no JSON skill object."""

    return li.attrs == {} and b"<" not in li.inner and text_content(li.inner) == ""


def _missing_li() -> LiSpan:
    return LiSpan(0, 0, 0, 0, 0, 0, {}, b"", b"")
