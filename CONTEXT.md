# Saga & Seeker Character Sheet Editing

This context describes the user-visible concepts involved in safely editing Saga & Seeker character sheets. It provides one shared vocabulary for product discussions, issues, tests, and documentation.

## Character Sheet

**Character sheet（キャラクターシート）**:
A Saga & Seeker HTML file containing one character's displayed information and embedded structured data.
_Avoid_: Save data, JSON file

**Original sheet（原本）**:
The character sheet selected as input and retained unchanged so the user can recover from an unsuccessful edit.
_Avoid_: Current file, output file

**Edited sheet（編集済みシート）**:
A separately saved character sheet containing changes confirmed by the user.
_Avoid_: Overwritten original

**Read-only state（読み取り専用）**:
A safety state used when the sheet can be displayed but the relevant structure cannot be classified or matched confidently enough to edit.
_Avoid_: Broken sheet, unsupported character

## Skills

**Skill slot（スキル枠）**:
One ordered position in the character sheet's visible skill area.
_Avoid_: Skill ID

**Registered skill（登録済みスキル）**:
A skill that occupies a skill slot and has corresponding character-sheet data.
_Avoid_: Filled row

**Default skill（デフォルトスキル）**:
A game-provided skill whose game identity is protected from ordinary name and description editing.
_Avoid_: Locked original skill

**Original skill（オリジナルスキル）**:
A player-created or game-AI-generated skill with a non-empty name and no default-skill type or key identity.
_Avoid_: `skN` skill, custom-ID skill

**Original skill requiring ID repair（ID修復が必要なオリジナルスキル）**:
An otherwise recognizable original skill whose ID is empty, non-textual, or duplicated exactly elsewhere.
_Avoid_: Invalid skill format

**Explicit empty skill（空スキル）**:
A registered placeholder that deliberately occupies a position so the game does not automatically add a generated skill there.
_Avoid_: Unused slot, missing skill

**Vacant skill slot（未使用枠）**:
A visual skill position with no corresponding registered skill, available for game-generated or manually created content.
_Avoid_: Empty skill, 空スロット

**Protected replacement（デフォルトスキルの置き換え）**:
The destructive conversion of a default skill into a new original skill, discarding the original default identity.
_Avoid_: Unlock, unprotect

**Skill ID（スキルID）**:
An exact, case-sensitive textual identity attached to a registered skill; its spelling or format alone does not determine the skill kind.
_Avoid_: Slot number, `skN` number

## Personality Keywords

**Personality keyword（性格キーワード）**:
A game-defined trait selected for a character from the supported catalog.
_Avoid_: Original personality, free-form keyword

**Personality slot（性格キーワード枠）**:
One of the six ordered positions available for a character's personality keywords.
_Avoid_: Keyword ID

**Personality catalog（性格キーワードカタログ）**:
The complete supported set of game-defined keyword records, each carrying its ID, name, system, and karma.
_Avoid_: User dictionary

**System（系統）**:
The broad keyword family: 力, 知恵, 富, 愛, or 法.
_Avoid_: Category when referring to karma

**Karma（傾向）**:
The moral grouping of a personality keyword: 美徳, 中庸, or 悪徳.
_Avoid_: System, rarity

**Contiguous selection（連続選択）**:
A personality arrangement in which every selected keyword precedes every unselected slot.
_Avoid_: Arbitrary sparse selection

## Memories

**Memory（思い出）**:
One ordered memory object retained in `data.memories`, whether or not its
position is visible in the standalone HTML.
_Avoid_: Memory slot, displayed memory

**Normal memory（通常思い出）**:
A non-placeholder memory containing the character's memory content and an
identity that is retained exactly unless the user explicitly changes the
memory.
_Avoid_: Filled slot

**Placeholder memory（空白保持枠）**:
The game's dedicated `isPlaceholder: true` memory object that deliberately
keeps a memory position blank and prevents automatic population. Its empty ID
is valid and may be duplicated.
_Avoid_: Empty memory, hyphen memory, missing memory

**Visible memory slot（表示思い出枠）**:
One of the six direct-child `li` positions in `ul#memories-value`. It displays
the same-position object among the first six memories, or remains blank for a
placeholder or missing position.
_Avoid_: Memory object

**Off-screen memory（JSON専用思い出）**:
A memory at array position seven or later that remains in `data.memories` but
has no corresponding standalone-HTML `li`.
_Avoid_: Deleted memory, hidden slot

**Memory boundary（思い出表示境界）**:
The boundary between array positions zero through five, which determine the six
HTML slots, and positions six onward, which exist only in JSON.
_Avoid_: Six-memory limit

**Replace with placeholder（空白保持枠へ置換）**:
An explicit operation that keeps the array position and total count while
replacing a normal memory with the complete placeholder-memory structure.
_Avoid_: Delete

**Remove from list（一覧から削除）**:
An explicit operation that removes the memory object and decreases the array
length.
_Avoid_: Clear, replace with placeholder

## Change State

**Baseline（基準状態）**:
The values established by a successful load or save and used to determine whether the current editor contents have changed.
_Avoid_: Change counter

**Unsaved changes（未保存の変更）**:
Current skill or personality values that differ from the baseline.
_Avoid_: Edit event count

## Profile Comparison

**Profile accordion（プロフィール折り畳み）**:
The normal basic-information view that keeps all seven profile field names
visible and independently expands or collapses their live editors. Accordion
state and splitter size are presentation state, not draft changes.
_Avoid_: Copied field, dropdown-only profile navigation

**Profile comparison（プロフィール比較）**:
A pair of synchronized views that expose two different profile fields at the
same time and optionally move into a separate window. Both views edit the same
character-sheet draft.
_Avoid_: Copied profile, second draft

**Personality reference（性格キーワード参照）**:
The live, read-only list of currently selected personality keywords shown next
to the profile comparison editors.
_Avoid_: Profile personality, editable keyword copy

## Markdown Interchange

**AI Markdown（AI向けMarkdown）**:
A lossy, human- and AI-readable export of supported semantic character data.
It is not a character-sheet archive and does not contain images or internal
identifiers.
_Avoid_: Markdown backup, reversible export

**Markdown import plan（Markdown取込プラン）**:
The validated preview of known Markdown headings before a new character sheet
is generated. Errors block creation; warnings require user review.
_Avoid_: Loaded sheet, automatic repair

**Partial restoration（部分取込）**:
Creation of a new sheet from the name, seven profile fields, six visible
statuses, catalog personality keywords, and at most six skills found in
Markdown. Images, memories, charm, IDs, timestamps, and skill identity are not
restored.
_Avoid_: Round trip, original restoration
