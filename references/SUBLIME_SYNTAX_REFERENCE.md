**Sublime Syntax Reference**

Purpose

This is a compact local reference intended for an LLM to generate or edit
.sublime-syntax files. It summarises the YAML structure, keys, behaviours,
examples and common pitfalls. Use it as a quick cheat-sheet when authoring
syntaxes for Sublime Text.

**Overview**

- Syntax files are YAML (use `%YAML 1.2` header) named `*.sublime-syntax`.
- A syntax assigns scopes (e.g. `keyword.control.c`) to matched text. Color
  schemes map scopes to styles.
- The file must define a `main` context — the starting context.
- Regex engine: Oniguruma. Matches run on one line at a time.
- Tabs are not allowed in `.sublime-syntax` files (use spaces).

Minimal example

```yaml
%YAML 1.2
---
name: C
file_extensions: [c, h]
scope: source.c

contexts:
  main:
    - match: \b(if|else|for|while)\b
      scope: keyword.control.c
```

**Header Keys (top-level)**

- `name`: displayed name for the syntax (optional).
- `file_extensions`: list of extensions (strings). Use full filename including
  leading `.` for names like `.gitignore`.
- `hidden_file_extensions`: same as above but hidden from file dialogs.
- `first_line_match`: regex matched against the first line for extensionless files.
- `scope`: default scope for whole file (e.g. `source.lang`).
- `version`: 1 or 2. New syntaxes should use `2` (fixes several scope bugs).
- `extends`: package path or list of package paths to inherit from
  (e.g. `Packages/JavaScript/JavaScript.sublime-syntax`).
- `hidden`: if true, syntax not shown in the menu but can be included.

**Contexts**

- `contexts:` maps context names to ordered lists of patterns.
- Every context is processed using the context stack. `push`, `pop`, `set`
  control stack behavior.
- When multiple patterns match at the same position, the leftmost match wins.
  When multiple patterns match at equal leftmost positions, the first
  defined pattern wins.

Meta patterns (must come first in a context)

- `meta_scope`: scope applied to all text while this context is on the stack.
- `meta_content_scope`: same but does not apply to the trigger text that
  pushed the context.
- `meta_include_prototype`: `false` prevents the `prototype` context from
  being auto-included into this context.
- `clear_scopes`: integer or `true`, removes scope names from current stack
  before applying `meta_scope`/`meta_content_scope`. Useful for embedding.
- `meta_prepend` / `meta_append`: control how duplicate contexts are merged
  during inheritance.

Common match/action keys

- `match`: regex to match (single-line). Quote when containing `# : - { [ >`.
- `scope`: scope assigned to the matched text.
- `captures`: map capture group numbers to scopes.
- `push`: push one or more contexts (or an inline anonymous context).
- `pop`: `true` to pop one context or an integer to pop multiple.
- `set`: pop current context, then push the specified context(s).
- `embed`: push a single context from another syntax. Requires `escape`.
- `escape`: regex to exit an `embed` region. Backreferences refer to this
  match's capture groups.
- `embed_scope`: scope applied to text between match and `escape`.
- `escape_captures`: capture scopes for the escape pattern (0 is whole match).
- `branch`: list of contexts attempted in order; used for ambiguous/multi-line
  constructs. `branch_point` marks the branch start. `fail` triggers retry.

Single-exclusive behavior: Only one of `push`, `pop`, `set`, `embed`, or
`branch` may be specified for a match.

Examples (short)

- Capture groups:

```yaml
- match: ^\s*(#)\s*\b(include)\b
  captures:
    1: meta.preprocessor.c
    2: keyword.control.include.c
```

- Push and string context:

```yaml
main:
  - match: '"'
    push: string

string:
  - meta_scope: string.quoted.double
  - match: \\.
    scope: constant.character.escape
  - match: '"'
    pop: true
```

- Embed a language (HTML -> JavaScript):

```yaml
- match: '<script>'
  push: Packages/JavaScript/JavaScript.sublime-syntax
  with_prototype:
    - match: (?=</script>)
      pop: true
```

- Variables usage:

```yaml
variables:
  ident: '[A-Za-z_][A-Za-z0-9_]*'

contexts:
  main:
    - match: '\b{{ident}}\b'
      scope: variable.name
```

**Include Patterns**

- `- include: <context>` inserts patterns from another context at that point.
- To include a context from another syntax: `include: scope:source.html`
- `apply_prototype: true` tells the include to also inject the other
  syntax's prototype (unless the included context disables it).

**Prototype Context**

- A special `prototype:` context is auto-included at the top of every
  context unless that context sets `meta_include_prototype: false`.
- Use `prototype` for things like comments that should be available everywhere
  except in contexts (e.g., strings) where they are invalid.

**Including External Syntax Files**

- Use `push: Packages/Name/Name.sublime-syntax` to enter the `main`
  context of another syntax.
- `with_prototype` lists patterns that will be inserted into every context of
  the included syntax (useful for injecting exit lookaheads like `(?=</tag>)`).

**Inheritance**

- `extends`: a single package path or list of package paths. Inherited items
  include `variables` and `contexts`. Other top-level keys are not inherited.
- Variable inheritance: variables are merged and later definitions override.
- Context inheritance: contexts are merged; duplicate context names are
  overridden or can be combined using `meta_prepend`/`meta_append`.
- Multiple inheritance: allowed but parents must be derived from the same base
  and are processed in order.



**Performance & Practical Tips**

- Keep regexes single-line; multi-line constructs should be handled via
  branching, embedding, or explicit contexts.
- Branches cause reprocessing and may rewind up to 128 lines on `fail`.
  Order branch contexts by likelihood for performance.
- Meta patterns must be listed first in contexts.
- Quote regexes when they contain YAML-sensitive characters.
- Prefer minimal, precise regexes to avoid accidental matches.
- Use `prototype` to avoid repeating common constructs (comments, literals).

**Common Pitfalls & Compatibility Notes (Version 1 → 2)**

- `embed_scope` stacking: in version 1 the embedded syntax scope was
  combined with `embed_scope`; version 2 only keeps `embed_scope` unless
  `embed_scope` is omitted.
- `set` with `meta_content_scope` differences: `set` historically applied
  the popped context's `meta_content_scope` incorrectly in v1 — target v2.
- `clear_scopes` behavior when pushing multiple targets: v1 summed
  `clear_scopes` from all targets incorrectly. Prefer v2 semantics.
- Capture group ordering bug: in some cases a lower-numbered capture that
  matches text after a higher-numbered capture may not receive its scope in v1.

If possible, author new syntaxes with `version: 2` to avoid these legacy
issues.

Try to avoid things like lookbehinds, they are bad for performance.

**Troubleshooting Checklist**

1. Is `main` context present? If not, add it.
2. Are regexes single-line and correctly quoted where needed?
3. Did you forget to `pop` after `push`ing a temporary context?
4. Use `SYNTAX TEST` files to assert scopes rather than manual inspection.
5. If embedding other syntaxes, ensure you use `with_prototype`/`escape`
   patterns so the parent syntax can regain control.
