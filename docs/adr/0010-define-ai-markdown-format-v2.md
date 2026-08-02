# Define AI-oriented Markdown format v2 before implementing it

Status: accepted

The desktop application remains version `2.0.0`; this decision defines the
independent **AI向けMarkdown形式 v2**. Version 1 allowed free text to collide
with Markdown headings and let unmarked input enter the normal parser without
consent. Version 2 fixes the complete structure, makes text values opaque
blocks, separates lexical format detection from parsing, and normalizes
interchange line endings to LF.

## Line-ending decision

Two options were considered:

1. Preserve every CR, LF, and CRLF sequence with a custom escape codec.
2. Normalize CRLF and lone CR to LF when exporting and importing AI-oriented
   Markdown.

Option 2 is selected. This format is a human- and AI-oriented intermediate, not
an archive. Editors and AI tools routinely change physical line endings, while
preserving CRLF would add syntax and failure modes without restoring omitted
images, identities, or memories.

The Markdown byte buffer is never edited in place. Decoding produces a separate
semantic string. The application also does not modify the current HTML sheet,
its original bytes, or its unsaved draft until parsing, preview, and new-sheet
creation have all succeeded.

## Lexical constants

All structural lines use exact, case-sensitive text:

```text
V2_MARKER  = <!-- saga-seeker-ai-markdown:2 -->
V1_MARKER  = <!-- saga-seeker-ai-markdown:1 -->
TEXT_START = <!-- saga-seeker-text:start -->
TEXT_END   = <!-- saga-seeker-text:end -->
```

Input is UTF-8 with an optional BOM and a maximum size of 8 MiB. After decoding,
CRLF and lone CR are converted to LF. The BOM is not a line. The v2 or v1
format marker is valid only on physical line 1; blank lines or comments before
it make its position invalid.

Format detection is a lexical pass, not character-data parsing. It tracks
`TEXT_START` and `TEXT_END` lines before looking for format markers. Marker-like
lines inside a text block are ignored. An escaped `\TEXT_END` line does not end
the block.

Detection returns exactly one of:

| Classification | Rule |
| --- | --- |
| `CANONICAL_V2` | One v2 marker on line 1 |
| `LEGACY_MARKED_V1` | One v1 marker on line 1 |
| `LEGACY_UNMARKED` | No marker outside text blocks |
| `INVALID_MARKER_POSITION` | One known marker exists outside a block but is not on line 1 |
| `UNKNOWN_VERSION` | One unknown-version marker exists outside a block |
| `DUPLICATE_MARKER` | The same version marker occurs more than once outside blocks |
| `MIXED_VERSION_MARKERS` | Different version markers occur outside blocks |
| `MALFORMED_TEXT_BLOCK` | An outside-block end marker or an unclosed text block is found |

`MIXED_VERSION_MARKERS` takes precedence over duplicate and position errors.
`DUPLICATE_MARKER` takes precedence over position errors. A single unknown
version is `UNKNOWN_VERSION` regardless of its line. Marker-like text inside a
block never contributes to duplicate, mixed, unknown, or position detection.

Only `CANONICAL_V2` enters the normal parser. `LEGACY_MARKED_V1` and
`LEGACY_UNMARKED` require explicit consent and `allow_legacy=True`. All other
classifications are blocking errors.

## Canonical structure

Outside text blocks, blank lines are permitted only between the following
grammar elements. The canonical writer emits exactly one blank line between
elements. No unrecognized nonblank line is permitted. In the grammar below,
`line(X)` means the exact text `X` followed by LF, and `blank_lines` means zero
or more empty physical lines.

```ebnf
document       = line(V2_MARKER), line(H1), blank_lines,
                 name_section,
                 profile_section,
                 personality_section,
                 status_section,
                 skills_section,
                 memories_section ;

blank_lines    = { NL };

H1             = "# Saga & Seeker キャラクター" ;

name_section   = line("## キャラクター名"),
                 text_block, blank_lines ;

profile_section =
                 line("## キャラクター詳細"), blank_lines,
                 profile_field_1, profile_field_2, profile_field_3,
                 profile_field_4, profile_field_5, profile_field_6,
                 profile_field_7 ;

profile_field_1 = line("### 基本設定"), text_block, blank_lines ;
profile_field_2 = line("### 外見"), text_block, blank_lines ;
profile_field_3 = line("### 性格"), text_block, blank_lines ;
profile_field_4 = line("### 口調"), text_block, blank_lines ;
profile_field_5 = line("### 経歴"), text_block, blank_lines ;
profile_field_6 = line("### 特技と役割"), text_block, blank_lines ;
profile_field_7 = line("### その他の特徴"), text_block, blank_lines ;

personality_section =
                 line("## 性格キーワード"), blank_lines,
                 [ personality_lines ], blank_lines ;
personality_lines = line(personality_line),
                 { line(personality_line) } ;
personality_line =
                 "- 枠", slot_1_to_6, ": ", catalog_keyword_name ;

status_section = line("## ステータス"), blank_lines,
                 line("- 筋力: ", rank),
                 line("- 耐久力: ", rank),
                 line("- 知力: ", rank),
                 line("- 精神力: ", rank),
                 line("- 素早さ: ", rank),
                 line("- 運: ", rank),
                 blank_lines ;
rank            = "E" | "D" | "C" | "B" | "A" | "S" ;

skills_section = line("## スキル"), blank_lines,
                 { skill_entry }, blank_lines ;
skill_entry    = line("### スキル ", positive_index_1_to_6),
                 line("#### 名前"), text_block, blank_lines,
                 line("#### 説明"), text_block, blank_lines ;

memories_section =
                 line("## 思い出"),
                 line(MEMORY_NOTICE), blank_lines,
                 { memory_entry }, blank_lines ;
MEMORY_NOTICE  = "> このセクションはAI参照用です。Markdownから新規作成しても思い出は復元されません。" ;
memory_entry   = line("### 思い出 ", positive_index),
                 line("#### タイトル"), text_block, blank_lines,
                 line("#### 概要"), text_block, blank_lines,
                 line("#### 場所"), text_block, blank_lines,
                 line("#### 意図"), text_block, blank_lines,
                 line("#### 結果"), text_block, blank_lines,
                 line("#### タグ（JSON）"),
                 line(json_string_array), blank_lines ;
```

The H1 and six H2 strings are mandatory and occur exactly once in the displayed
order. The seven profile H3 strings are mandatory in the displayed order.
Skills are numbered contiguously from 1 and contain zero to six entries.
Memories are numbered contiguously from 1 and have no format-level upper bound.
Skill and memory titles are values, never heading text. The H4 strings and order
shown above are also fixed.

Personality slots start at 1, are contiguous, unique, and use exact catalog
names. An empty personality section has no placeholder line. Status always has
all six lines. An empty skill or memory section has no H3 entry.

Blank lines immediately after `## 性格キーワード` and immediately before
`## ステータス` are structural separators. Once the first personality line
has appeared, no blank line may occur before the last personality line. Thus a
blank line between two personality entries is an error, not a silently removed
separator.

## Text-block codec

A block is serialized as:

```ebnf
text_block   = TEXT_START, NL, encoded_line,
               { NL, encoded_line }, NL, TEXT_END ;
encoded_line = { encoded_character } ;
```

Before encoding, CRLF and lone CR are converted to LF. Splitting on LF retains
empty leading, trailing, and consecutive segments. Each content line is encoded
as follows:

1. A line exactly equal to `TEXT_START` or `TEXT_END` is prefixed with `\`.
2. In every other line, each literal `\` is encoded as `\\`.
3. Any other single-backslash escape is invalid.

The parser treats H1–H4 text, bullets, `（未入力）`, HTML, and other Markdown
syntax inside a block as ordinary content. A standalone unescaped `TEXT_END`
line is the only successful block terminator. A standalone unescaped
`TEXT_START` within a block is a noncanonical reserved line and is an error.

Canonical examples:

```text
empty:
<!-- saga-seeker-text:start -->

<!-- saga-seeker-text:end -->

leading LF:
<!-- saga-seeker-text:start -->

first
<!-- saga-seeker-text:end -->

trailing LF:
<!-- saga-seeker-text:start -->
last

<!-- saga-seeker-text:end -->

consecutive LFs:
<!-- saga-seeker-text:start -->
first


last
<!-- saga-seeker-text:end -->

literal markers and backslash:
<!-- saga-seeker-text:start -->
\<!-- saga-seeker-text:start -->
\<!-- saga-seeker-text:end -->
path\\name
### this is content, not a heading
<!-- saga-seeker-text:end -->
```

The final example decodes to literal start marker, literal end marker,
`path\name`, and the H3-looking content line. `\q`, a trailing single `\`, an
unescaped reserved start line, and an unclosed block are errors.

Character name and skill name blocks must decode without LF. They are never
silently converted to spaces. The seven profile fields, skill descriptions,
and all five memory text fields may contain LF. In canonical v2,
`（未入力）` inside a block is literal text; only an empty block means empty.

## Legacy boundary and diagnostics

Legacy processing order is fixed:

1. Read bytes.
2. Detect format only.
3. Display that the file is legacy.
4. Require the user action labelled `旧形式として解析する`.
5. Parse with `allow_legacy=True`.
6. Show the detailed preview.
7. Confirm non-restored fields and limitations.
8. Create a new sheet.

The normal import path never parses legacy content before step 4.

The v1 marker and unmarked legacy dialect use their existing H2/H3 field names.
The recognized H2 strings are `キャラクター名`, `キャラクター詳細`,
`性格キーワード`, `ステータス`, `スキル`, and `思い出`. The only recognized
profile H3 strings are the seven canonical profile field names. Recognized
headings may occur at most once. Any other structural H2 or H3 is an error;
its body is never silently discarded. Skills are unambiguous only when each
skill uses an H3 name; a bullet-only skill section is an error. Bullets inside
an H3 skill description remain description text.

Legacy warnings:

- a missing profile field becomes empty;
- a missing status becomes `E`;
- image and memories are not restored; and
- no personality keyword was specified.

Legacy errors:

- bullet-only or otherwise ambiguous skills;
- duplicate recognized headings;
- malformed or unknown status lines;
- an unknown structural H2 or profile H3 heading;
- an unknown personality keyword;
- CR or LF in a resulting character or skill name; and
- any structure with more than one possible interpretation.

Missing information is not treated as equivalent to ambiguous information.
Warnings remain visible in preview; errors block creation.

## Memory restoration boundary

The canonical memory section is required and structurally validated so its
free text cannot be confused with structure. Import records only the number of
detected normal memory entries. It never copies memories into the generated
sheet.

The export notice is fixed and machine checked. Preview states both:

```text
思い出: N件検出
取込結果: 復元されません
```

Images, memories, internal IDs, timestamps, skill identities, and charm remain
outside partial restoration.

## Consequences

- Application version `2.0.0` and AI-oriented Markdown format version `2` must
  not be described as the same version.
- Errors, previews, audits, and documentation use the full Japanese label
  `AI向けMarkdown形式 v2`, not bare `v2`.
- Format detection, canonical parsing, and legacy parsing remain separate code
  paths with separate tests.
- Parser and GUI implementation may begin only after this ADR is committed.
