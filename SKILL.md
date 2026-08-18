---
name: sublime-syntax-test-yaml
description: >
  Write, test, and debug Sublime Text .sublime-syntax files using a YAML-based
  test DSL and Sublime's own official syntax_tests binary, with an
  LLM-friendly failure report. Use this skill whenever asked to write a
  Sublime Text syntax for a language, add syntax highlighting for X in
  Sublime Text, create or edit a .sublime-syntax file, define scopes or
  contexts for a Sublime Text package, or debug a failing syntax_test /
  .sublime-syntax-test.
license: Unlicense (public domain) — see LICENSE.md
compatibility: >
  Requires bash, and either curl or wget, plus network access to
  download.sublimetext.com to fetch Sublime's official syntax_tests binary
  (Linux x64 only; pinned to build 4200 by default, overridable). Requires
  uv (https://astral.sh/uv) to run the two bundled Python scripts without
  manual venv setup.
---

# Sublime Text syntax, test-driven

Sublime ships an official test format (`syntax_test_*` files) and test
binary, but that format is very hard for an LLM to read or write directly —
it depends on exact vertical/column alignment between a source line and a
caret line below it. This skill provides a YAML DSL for writing those tests,
and a parser that turns the binary's raw failure output into a flat,
unambiguous report.

The loop:

```
tests/*.yaml  --[scripts/yaml2syntaxtest.py]-->  package/tests/syntax_test_*
                                                          |
                                                          v
                                      Sublime's syntax_tests binary
                                                          |
                                                          v
                          raw pass/fail output  --[scripts/parse_syntax_test.py]-->  LLM-readable failure list
```

Everything below other than Step 3's one-time setup happens in the
**target project** being worked on — not inside this skill's own folder.
Find this skill's own root (the directory containing this file) via its own
path once invoked; call it `$SKILL_ROOT` below.

## Step 0 — Establish language, file locations, and package name

If the request doesn't already make these obvious, ask the user (don't
guess):

1. **Language** being written a syntax for.
2. **Where the `.sublime-syntax` file should live** in the target project.
   If there's no existing convention, create a `package/` directory at the
   target project's root laid out the way Sublime itself expects a package,
   e.g. `package/<Language>.sublime-syntax`. `package/tests/` is a generated
   output directory — don't hand-edit it. Step 4 overwrites one file there per
   `tests/*.yaml`, but it does **not** clear the directory first: renaming or
   deleting a YAML source leaves its stale `syntax_test_*` behind, and the
   binary keeps running it. Delete the orphan by hand when that happens (and
   consider gitignoring `package/tests/`).
3. **The package name** — the first path segment after `Packages/` that the
   YAML tests' `syntax:` field will reference, e.g.
   `syntax: "Packages/RSpec/RSpec.sublime-syntax"` implies package name
   `RSpec`. This must exactly match the `package_name` passed to
   `setup_syntax_tests.sh` in Step 3, because Sublime's test binary resolves
   `Packages/<name>/...` against a symlink named `<name>`.
4. **Whether a grammar/spec document exists** to seed from. If so, read it,
   but remember a grammar validates syntax and a `.sublime-syntax` file
   assigns *scopes* to token positions — this is not about writing a
   validator.

Also create a `tests/` directory at the target project root for the YAML
test sources (distinct from the generated `package/tests/`).

## Step 1 — Read the reference docs

Before writing or editing the syntax file, read (paths relative to
`$SKILL_ROOT`, not the target project):

- `references/SUBLIME_SYNTAX_REFERENCE.md` — YAML syntax-file structure,
  keys, behaviors, common pitfalls.
- `references/SCOPE_NAMING_GUIDELINES.md` — how to name scopes so they stay
  compatible with existing color schemes and other packages.
- `references/SYNTAX_DEVELOPMENT_TIPS.md` — patterns for contexts, pushdown
  automata pitfalls, scope doubling, etc.

## Step 2 — Write YAML tests

Tests live in the target project's `tests/*.yaml` (one file per logical
group is fine). DSL, by example:

```yaml
syntax: "Packages/RSpec/RSpec.sublime-syntax"   # required — see Step 0.3
comment_char: "#"                                # optional, default "#"
tests:
  - line: "describe Some::Tag do"
    assertions:
      - span: "describe"
        scopes: [keyword.other.rspec.behaviour, meta.rspec.behaviour]
      - span: "Some::Tag do"
        scopes: [meta.rspec.behaviour]
        nth: 0                                   # optional, 0-indexed, default 0
```

`span` is matched literally against `line`; `nth` picks which occurrence when
it appears more than once (e.g. repeated `.` operators). Full worked
examples, including a `comment_char: "//"` variant for C-style languages,
are in `examples/yaml/single_char_comment.yaml` and
`examples/yaml/double_char_comment.yaml`.

Aim for coverage like Sublime's own built-in syntaxes: every language
feature, from the simplest case to edge cases (nested constructs,
unterminated strings, escapes, comments containing lookalike tokens, etc).
Make changes to the syntax file *small* between test runs so a new failure
is easy to attribute.

## Step 3 — One-time setup: fetch the test binary

From the **target project's root**, run:

```bash
bash "$SKILL_ROOT/scripts/setup_syntax_tests.sh" [build] [target_dir] [package_path] [package_name]
```

All arguments are optional:

| Arg / env var | Default | Meaning |
|---|---|---|
| 1st arg or `SUBLIME_BUILD` | `4200` | Sublime Text build number for the test binary. `4200` is the only build this toolset has actually been verified against — only change it if there's a specific reason to. |
| 2nd arg or `SYNTAX_TESTS_DIR` | `./st_syntax_tests` | Where to download/extract the binary (relative to the current directory, i.e. the target project). |
| 3rd arg | *(none)* | Path to the package directory to test (e.g. `package/` from Step 0). If given, it's symlinked in as `Data/Packages/<package_name>`. |
| 4th arg | `basename` of the 3rd arg | Explicit name for that symlink — must match what the YAML `syntax:` fields expect (Step 0.3). |

Re-running this script is safe and cheap — it skips the download if the
binary is already present (set `FORCE=1` to force re-download/re-link). This
script only supports Linux x64 (Sublime doesn't publish this test binary for
other platforms); network access to `download.sublimetext.com` is required
the first time.

## Step 4 — Run tests in a loop

```bash
bash "$SKILL_ROOT/scripts/run_tests.sh" --tests-dir tests --package-tests-dir package/tests
```

Defaults match Step 0's layout (`./tests`, `./package/tests`,
`./st_syntax_tests`), so when already standing in the target project root
with that layout, it can be run with no arguments. This:

1. Converts every `tests/*.yaml` into `package/tests/syntax_test_*`.
2. Runs Sublime's `syntax_tests` binary.
3. Pipes the result through `scripts/parse_syntax_test.py`, printing one
   block per failure:
   - File under test
   - Text of the line under test
   - Span under test
   - Expected scope(s)
   - Got scope(s)
   - A trailing `--- Summary: N failure(s) detected ---` line.

The script's own exit code reflects whether the underlying test run passed —
check it instead of grepping output. A YAML file that fails to convert (bad
YAML, a `span` that doesn't occur in its `line`) is a hard error: the run
exits 1 without invoking the binary, rather than silently skipping that file
and reporting green.

Test files may freely mix comment characters. Step 1 of the run records each
generated file's `comment_char` in `package/tests/.comment_chars.json`, and
the parser reads that manifest to pick the right character per failure, so no
batching or per-style runs are needed. `--comment-char` remains only as the
fallback for files with no manifest entry.

## Step 5 — Interpret failures and iterate

Each failure block from Step 4 shows: what line, what span, what scope was
*expected*, and what scope Sublime's engine *actually* produced. Common
causes, roughly in order of likelihood — see
`references/SYNTAX_DEVELOPMENT_TIPS.md` for detail on each:

- A context was pushed but never popped, so it "leaks" into following lines.
- Scope doubling (e.g. a `meta_scope` applied twice, once by a parent context
  and once by a child).
- Wrong match ordering inside a context (a broader pattern shadows a more
  specific one that should run first).
- A `push`ed context has no bail-out, so a truncated/invalid buffer never
  returns to `main`.

Make one small change to the `.sublime-syntax` file, rerun Step 4, and watch
the failure count trend to zero. If the parsed output is confusing for a
particular case, write a short throwaway script against the raw binary
output rather than guessing from column-aligned caret text.

## Notes on `mise.toml`

This skill repo ships a `mise.toml` with `setup`/`gen-tests`/`test` tasks
that call the same scripts. Those tasks only work as convenience shortcuts
when standing *inside this skill's own checkout* (their defaults are
relative to wherever `mise.toml` itself lives) — once this folder is
symlinked into a harness's skill-discovery path and the work is happening in
a different target project, always invoke `scripts/setup_syntax_tests.sh`
and `scripts/run_tests.sh` directly with explicit paths as shown above,
rather than `mise run ...`. If the user uses mise, they may be interested in
adding those tasks to their project. Confirm with them.
