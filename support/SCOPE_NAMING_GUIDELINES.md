SCOPE NAMING GUIDELINES
======================

Purpose
-------
- Provide concise, actionable guidelines for naming scopes in syntax definitions and color schemes.
- Maintain compatibility with Sublime Text / TextMate grammars and make color schemes broadly usable.

Principles
----------
- Scopes are dotted strings, ordered least-to-most specific. Example: `keyword.control.php`.
- The syntax name (language) should be the last segment of a scope when applicable: `keyword.control.ruby`.
- Prefer the smallest correct change: create clear, predictable scopes that other packages and themes can match.

General Rules
-------------
- Use top-level categories: `comment.`, `constant.`, `entity.`, `invalid.`, `keyword.`, `markup.`, `meta.`,
  `punctuation.`, `source.`, `storage.`, `string.`, `support.`, `text.`, `variable.`
- Keep `meta.` scopes for structure and tooling (preferences/plugins). Avoid styling `meta.*` directly.
- Apply a single `meta.*` scope to a region and use child scopes for parts; do not stack the same `meta` scope.
- Use `punctuation.definition.*` and `punctuation.section.*` for delimiters and boundary characters.
- For interpolated strings: clear the outer `string.*` scope (using `clear_scopes:`) and add
  `meta.interpolation` + `punctuation.section.interpolation.begin/end` with `source.*.embedded` inside.

Naming Conventions & Examples
----------------------------
- Comments
  - `comment.line` (single-line)
  - `comment.block` (multi-line)
  - `comment.block.documentation` (doc comments)
  - `punctuation.definition.comment` for the comment markers

- Constants
  - `constant.numeric` and variants: `constant.numeric.integer`, `constant.numeric.float`,
    type-specific variants like `.hexadecimal`, `.binary`, `.decimal`
  - `constant.language` (booleans, null)
  - `constant.character.escape` (string escapes)

- Entities (names)
  - Types/classes/interfaces: `entity.name.class`, `entity.name.struct`, `entity.name.interface`
  - Functions: `entity.name.function`, `entity.name.function.constructor`
  - Namespaces: `entity.name.namespace`
  - Constants (named): `entity.name.constant`
  - HTML/XML tags: `entity.name.tag`
  - Attribute names: `entity.other.attribute-name`
  - Avoid unnecessary nesting such as `entity.name.type.class`.

- Keywords & Operators
  - `keyword.control` (control flow)
  - `keyword.control.conditional`, `keyword.control.import`
  - `keyword.operator` with variants: `.assignment`, `.arithmetic`, `.bitwise`, `.logical` or
    `keyword.operator.word` for word-operators (`and`, `or`, `not`)
  - `punctuation.definition.keyword` for punctuation that is part of a keyword

- Markup (text syntaxes)
  - `markup.heading`, `markup.list.numbered`, `markup.list.unnumbered`
  - `markup.bold`, `markup.italic`, `markup.underline`
  - `markup.raw.block` / `markup.raw.inline` for code blocks

- Meta (structural)
  - `meta.function`, `meta.function.parameters`, `meta.class`, `meta.namespace`, `meta.tag`, etc.
  - `meta.function-call` for a full function invocation region

- Strings
  - `string.quoted.single`, `string.quoted.double`, `string.quoted.triple`, `string.quoted.other`
  - `meta.string` for the entire string region (avoid styling `meta.string` when possible)
  - `string.regexp` for regex literals, `string.unquoted` for unquoted strings

- Variables
  - Generic: `variable.other` (use `.readwrite` variant if useful)
  - Parameters: `variable.parameter`
  - Members/properties: `variable.other.member`
  - Invoked function names: `variable.function` (definitions should be `entity.name.function`)
  - Language-reserved: `variable.language`

Color Scheme Guidance
---------------------
- Style broad selectors before specific ones. Avoid over-specific selectors that only suit one syntax.
- Minimal recommended coverage (baseline selectors every theme should provide):
  - `entity.name`, `entity.other.inherited-class`, `entity.name.section`, `entity.name.tag`,
    `entity.other.attribute-name`
  - `variable`, `variable.language`, `variable.parameter`, `variable.function`
  - `constant`, `constant.numeric`, `constant.language`, `constant.character.escape`
  - `storage.type`, `storage.modifier`
  - `support`, `keyword`, `keyword.control`, `keyword.operator`, `keyword.declaration`
  - `string`, `comment`, `invalid`, `invalid.deprecated`
- Do not rely on coloring specific `entity.name.*` entries for new or unknown entity types. Provide
  a base `entity.name` color and override only `entity.name.tag` and `entity.name.section` where needed.

Practical Tips
--------------
- Keep scope names predictable and language-neutral where possible. Use the language as the final
  segment when needed (e.g. `.python`, `.php`).
- Use `meta.*` for tooling and grouping; use specific child scopes for visual styling.
- Avoid excessive fragmentation: prefer a clear and limited set of scopes rather than many highly
  specific variants that make themes brittle.
- Test syntaxes with several popular color schemes to ensure reasonable defaults are styled.

References
----------
- Based on Sublime Text scope naming recommendations and TextMate grammar conventions.

Example
-------
For a PHP `if` keyword and condition expression you might use:

```
keyword.control.conditional.php      # "if"
punctuation.definition.group.begin   # "("
meta.group                          # the condition group
variable.other                        # variables inside condition
punctuation.definition.group.end     # ")"
```

End of guidelines
