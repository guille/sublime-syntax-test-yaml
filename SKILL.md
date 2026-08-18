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
   Default to the layout a Sublime package actually ships as — the repo root
   *is* the package, because that's what Package Control installs:

   ```
   <Language>.sublime-syntax    # repo root, alongside Comments.tmPreferences etc.
   tests/syntax_test_*          # generated; tracked in git
   yaml_tests/*.yaml            # YAML sources for this DSL; tracked in git
   st_syntax_tests/             # the test binary; gitignored
   ```

   Track `tests/` rather than gitignoring it. It lets CI run the suite with
   nothing but the binary — no Python, no PyYAML, no copy of this toolkit —
   and it lets experienced contributors add a hand-written `syntax_test_*`
   with no YAML counterpart. Use `.gitattributes` `export-ignore` to keep
   `tests/`, `yaml_tests/` and dev files out of the shipped package archive.

   Step 4 overwrites one file in `tests/` per `yaml_tests/*.yaml`, but does
   **not** clear the directory first — deliberately, so hand-written tests
   survive. The cost is that renaming or deleting a YAML source leaves its
   stale `syntax_test_*` behind and the binary keeps running it. Delete the
   orphan by hand when that happens.
3. **The package name** — the first path segment after `Packages/` that the
   YAML tests' `syntax:` field will reference, e.g.
   `syntax: "Packages/RSpec/RSpec.sublime-syntax"` implies package name
   `RSpec`. This must exactly match the `package_name` passed to
   `setup_syntax_tests.sh` in Step 3, because Sublime's test binary resolves
   `Packages/<name>/...` against a directory named `<name>`.
4. **Whether a grammar/spec document exists** to seed from. If so, read it,
   but remember a grammar validates syntax and a `.sublime-syntax` file
   assigns *scopes* to token positions — this is not about writing a
   validator.

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

A `scopes:` list is emitted joined by `&`, an order-independent AND: every
listed scope must be present on the token, in any nesting order. That default
matters because the ways of combining scopes are *not* interchangeable, and
only one of them means "all of these".

Full operator set, per <https://www.sublimetext.com/docs/selectors.html>:

| Selector | Meaning |
|---|---|
| `a b` | descendant — `b` somewhere after `a` in the scope stack, not necessarily adjacent |
| `a & b` | AND, order-independent — what `scopes: [a, b]` emits |
| `a, b` / `a \| b` | **OR** (the two are identical) |
| `-a` | NOT |
| `(...)` | grouping |
| `a > b` | child — `b` immediately after `a`. **Avoid**, see below |

Precedence, highest first: `()`, `-`, `&`, `|`, `,` — otherwise left-to-right.
Matching is by dotted *prefix*: "for a selector to match a token's scope name,
all of its labels must be present in the same order", so bare `string` matches
`string.quoted.double.expr`. There are no wildcards or anchors.

Three consequences worth knowing, all verified against the build-4200 binary:

- **`a, b` is a near-useless assertion.** `bogus.zzz, string.quoted.double`
  *passes*, because OR is satisfied by the half that matches. Never hand-write
  a comma-separated scope string hoping for set semantics.
- **Don't use `>` at all yet.** It is documented, but it only exists in build
  4205, which is a dev build and not public at time of writing. On 4200 a `>`
  selector never matched — spaced, unspaced, or where the two scopes are
  provably adjacent — while the equivalent descendant selector passed. It fails
  silently as a plain non-match, so it reads like a syntax bug rather than an
  unsupported operator.
- **Subtraction composes safely with the list form**, since `-` binds tighter
  than `&`. Both `scopes: [string.quoted.double.expr, "- comment"]` and a
  single `["string.quoted.double.expr - comment"]` assert "is a string and is
  *not* a comment". Do this liberally — negative assertions are what pin down
  that `//` inside a string isn't a comment, or that `..` didn't match as an
  accessor. They catch the failures that positive assertions sail past.

Use a single string only to assert a nesting path deliberately.

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
| 3rd arg | *(none)* | Path to the package to test — with the Step 0 layout this is the repo root, `.`. If given, `Data/Packages/<package_name>` is created and each of its top-level entries symlinked in. |
| 4th arg | `basename` of the 3rd arg | Explicit name for that directory — must match what the YAML `syntax:` fields expect (Step 0.3). |

The 3rd arg is linked **entry by entry**, not as one symlink to the whole
directory, and the directory holding the binary is skipped. That is what lets
`st_syntax_tests/` live inside the repo root while the repo root is itself the
package. Symlinking the root wholesale instead puts the binary's own
`Data/Packages` back underneath `Data/Packages/<name>`; the binary then reaches
it through the link and prints

```
scan: .../Data/Packages/<name>/st_syntax_tests/Data/Packages has been seen
before, skipping (using inode) previous path: .../Data/Packages
```

and **exits 1 even though every assertion passed**. Since `run_tests.sh`
propagates that exit code, a fully green suite reports as a failure with no
failure blocks to explain it — check for this whenever the parsed output says
"No failures detected" but the exit code is 1.

Because entries are linked individually, re-run this script after adding a new
top-level file to the package. Re-running is safe, cheap and idempotent: it
skips the download if the binary is present, refreshes the entry links, and
prunes links whose source is gone (set `FORCE=1` to force re-download). This
script only supports Linux x64 (Sublime doesn't publish this test binary for
other platforms); network access to `download.sublimetext.com` is required
the first time.

## Step 4 — Run tests in a loop

```bash
bash "$SKILL_ROOT/scripts/run_tests.sh" \
  --tests-dir yaml_tests --package-tests-dir tests --comment-char "//"
```

Defaults are `./yaml_tests`, `./tests` and `./st_syntax_tests`, matching Step
0's layout, so when already standing in the target project root it can be run
with no arguments. This:

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

## Step 6 — Confirm a green run is actually green

A malformed assertion line is *ignored*, not failed, so "No failures detected"
does not by itself prove the assertions ran. Before reporting success, mutate
every generated assertion to a scope that cannot match and check that the
failure count equals the number of assertions:

```bash
# after a normal run, so package tests are up to date
grep -cE '(\^|<-)' tests/syntax_test_* | awk -F: '{s+=$2} END {print "assertions:", s}'
python3 - <<'EOF'
import glob, re
for f in glob.glob('tests/syntax_test_*'):
    out = []
    for line in open(f):
        m = re.match(r'^(\s*\S*\s*(?:\^+|<-)\s*)(.*)$', line.rstrip('\n'))
        out.append(m.group(1) + 'bogus.scope.zzz' if m and m.group(2) else line.rstrip('\n'))
    open(f, 'w').write('\n'.join(out) + '\n')
EOF
./st_syntax_tests/syntax_tests 2>&1 | grep -c 'error: scope does not match'
```

The two counts should match. Regenerate (Step 4) afterwards to undo the
mutation. Expect a small shortfall when source lines under test themselves
contain `^` or `<-` — an exponent operator or a regex literal inflates the
first count — so account for those before concluding an assertion is dead.

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

Don't add a `mise.toml` to the target project reflexively. When the scripts
live in this skill, such tasks are only aliases wrapping a path into a
gitignored `.claude/` directory — machine-specific, useless to any other
contributor, and no shorter than the command itself. It earns its place only if
the project vendors its own copies of the scripts at the repo root, so the
tasks reference tracked files. Either way, ask first.

For CI, don't reach for these scripts at all: with `tests/` tracked, the
official `SublimeText/syntax-test-action@v2` runs the suite against real
Sublime builds with no toolkit, Python or generation step involved.
