---
name: sublime-syntax-fuzzing
description: >
  Find scoping bugs in a Sublime Text .sublime-syntax that hand-written syntax
  tests miss, by dumping the scopes Sublime's own syntax_tests binary assigns
  and fuzzing with changes that must not alter them (identifier renames, soft
  keywords as names, line breaks). Use when asked to fuzz, stress-test or
  audit a Sublime syntax, check it against real-world code, or find leaking
  contexts or lookahead bugs.
license: Unlicense (public domain)
compatibility: >
  Needs the syntax_tests binary installed by the sublime-syntax-test-yaml
  skill's setup script (Linux x64; verified on build 4200), and uv
  (https://astral.sh/uv) for the Python scripts.
---

# Fuzzing a Sublime Text syntax

Curated syntax tests only check what someone thought to assert. This skill
finds the rest: contexts that leak, lookaheads that take a name for a keyword,
constructs that scope differently once split across lines. It doesn't need a
reference parser. Instead it applies changes that must not change the scopes
(*metamorphic testing*) and diffs the scopes before and after.

Scripts (`$SKILL_ROOT/scripts/`):

- `dump_scopes.py`: scopes of any source, as text, JSON, or a ready-to-paste
  YAML test block. Also a library (`Dumper`).
- `metamorphic.py`: library with no language knowledge. It builds variants
  from spans you rename or gaps you break, dumps and diffs them, and groups
  the results.
- `golden_dumps.py`: every token a syntax change re-scopes on a corpus,
  comparing a git revision with the working copy (Step 7).

Find this skill's root (the directory containing this file) from its path
once invoked; it's called `$SKILL_ROOT` below. Run and import the scripts
from there, and don't copy them into the target project: copies go stale.
The driver you write lives in the target project (e.g. `fuzz/`). It imports
the scripts by putting `$SKILL_ROOT/scripts` on `sys.path`, overridable by an
environment variable.

You write the language-specific part: a small lexer and the variant rules.
That's deliberate. A lexer for one language is about a hundred lines, and a
half-generic one causes more false positives than it saves.

## Step 1: Dump scopes

```bash
"$SKILL_ROOT/scripts/dump_scopes.py" --syntax X.sublime-syntax -c '//' file.x
"$SKILL_ROOT/scripts/dump_scopes.py" --syntax X.sublime-syntax -c '//' --json a.x b.x
"$SKILL_ROOT/scripts/dump_scopes.py" --syntax X.sublime-syntax -c '//' --yaml --line 12 file.x
```

It looks for the binary in `./st_syntax_tests` (or `--syntax-tests-dir`,
`SYNTAX_TESTS_DIR`). Each line it prints is `line:start-end  'text'  full
scope stack`, including each newline, whose scope is where leaks show up.

Two limits to know about:

- **A source line that looks like an assertion can't be dumped**: optional
  whitespace, the comment token, optional whitespace, then `^`, `<-` or `@`
  (e.g. `//@Deprecated(...)` with `//`). Real code has these (commented-out
  annotations), so check `Dumper.dumpable()` and skip them.
- **The comment token must start a real line comment in the language**,
  because the assertion lines are part of the scoped buffer. A context that
  pops at the next non-comment line can therefore behave slightly
  differently than in the editor.

`--yaml --line N` emits a test block for line N as it scopes *today* (the
lines before it become `prefix_lines`), for the sublime-syntax-test-yaml DSL.
Fix the wrong scopes in it before using it as a test.

## Step 2: Pick seeds

Use both kinds:

- **The curated test lines** (`metamorphic.yaml_seeds("yaml_tests")`: each
  block's `prefix_lines` + `line`). They're short and packed with edge
  cases, so diffs are easy to read.
- **A real-world corpus**: a mature open-source project in the language,
  shallow-cloned. It finds bug classes the curated lines never reach, such as
  leaks spanning several lines. Split files into chunks at top-level declarations (for
  brace languages: a blank line followed by a line at column 0, outside
  braces; a naive brace count is enough) and skip very long chunks. Short
  seeds make readable diffs and cheap variants.

Remove undumpable seeds first (`dumper.dumpable(seed.text)`): one bad source
fails its whole batch.

## Step 3: Write a lexer for the language

You need identifier spans for renames and code tokens for line breaks,
skipping comments, strings and quoted identifiers.

Inside string interpolation (`"${a.b}"`, `f"{x}"`), identifiers *are* code.
Rename them consistently, but don't break lines inside a template.

Lexer bugs show up as false positives, so when a report group looks absurd,
check the lexer first. Kotlin examples: `as?` split into `as` + `?`, `1e-8`
split at the `-`, a shebang treated as operators.

## Step 4: Generate variants

Each variant changes something that must not change any scope, and must
still be code someone would write: hits on unrealistic code are noise nobody
will fix. Diffs are reported only for the unchanged text, plus the renamed
spans compared as whole tokens.

**Alpha rename.** Give every identifier a fresh name of the same shape
(`metamorphic.alpha_rename`): same case at each position, same digits and
underscores, so heuristics like "Capitalised means type" see the same thing.
Never rename words the syntax mentions itself (`metamorphic.known_words`
reads them from the syntax's `match` patterns and variables): builtin types,
`self`/`this`/`it`, and so on. Expect **zero diffs**. A diff means the syntax
depends on a name it shouldn't. Run this first, because it also checks your
pipeline.

**Soft keywords as names.** Take the language's contextual keywords from its
lexical grammar (often a production like `IdentifierOrSoftKeyword`), then
keep only the ones a corpus actually uses as names (after `.`, after
`val`/`fun`, as calls). In Kotlin, `value`, `data`, `get`, `expect`, `catch`
and `out` qualify; `by`, `operator` and `const` don't. Rename one lowercase
identifier at a time to each of them (`metamorphic.rename` with a one-entry
mapping), sampling a fixed number per seed.

- Expect many **token** diffs. Often they're one broad bug: "a soft keyword
  is scoped as a keyword wherever it appears".
- The valuable diffs are the **context** ones: the rename breaks scopes
  *around* the token, which points to a lookahead or a leak.
- Known false positives: renaming an infix function or operator method
  changes the program.

**Line breaks (reflow).** Break one line at a place where the grammar allows
a newline (`metamorphic.break_line(seed, gap_start, gap_end, label)`). This
targets contexts that pop at end of line, and constructs whose scope is
decided by a token later on the same line. It tends to find the most bugs.
How hard the rules are depends on the language:

- **Free-form languages** (C, Java, C#, CSS): almost any token boundary
  outside strings, comments and preprocessor lines is safe.
- **Languages where newlines matter** (Kotlin, Swift, Go, Scala, JS/TS with
  ASI, Ruby, Python): derive the positions from the grammar's optional-newline
  spots (`NL*`, `{NL}`, `nls`, ...). Model the exceptions with a bracket
  stack:
  - no break before a call's `(`;
  - none after `return`;
  - none before `=` in a plain assignment;
  - no breaks inside some keywords' parentheses.

  For Python, only breaks inside brackets are safe.
- Prefer breaks people make: in argument lists, before `.` in call chains,
  after `=`. Breaking inside a type or between generic arguments is legal
  but rare.
- Label each point by its rule (`after (`, `before .`, `after modifier`), so
  report groups show which rule triggered.
- **Print a sample of the chosen break points and check them by hand before
  the first run.** A rule that's too broad shows up as hundreds of false
  diffs.

**Comments where people write them.** Add a line comment at the end of a
line (`foo(a, // why`), or a comment on its own line between two lines of a
construct (parameter lists, call chains, `when` entries, class bodies). Use
`metamorphic.replace_gap(seed, gap_start, gap_end, text, label)`, skipping
lines that end inside a multi-line string or comment. It targets contexts
that don't survive a comment at a line end. Don't insert `/* c */` between
arbitrary tokens: that finds lookaheads that can't see past a comment
(`foo /* c */ (1)`), which is code nobody writes.

**Wrapping.** Put the seed inside a class body, a function body and a lambda
(`metamorphic.wrap(seed, header, footer, label)`). Each seed char is then
expected to scope as the wrapper's stack plus its original stack, so only
real differences show. It targets "works at top level, breaks when nested".

- Skip seeds with lines that are only valid at top level (`package`,
  `import`, file annotations).
- Skip seeds with unbalanced brackets. Curated test lines are often
  fragments (`) {`, `}`), and a fragment's `}` closes the wrapper.
- Start a lambda wrapper with a statement (`run {` ⏎ `Unit`), so the seed's
  first line isn't read as lambda parameters.
- Complete declarations work best, so a corpus is the main target here.
  Curated fragments mostly give noise.

**Code being typed (recovery).** The editor shows half-typed code all the
time, and a syntax that doesn't recover breaks everything below the cursor.
Take two consecutive top-level declarations from one file as a seed, cut the
first one short after one of its tokens, and keep the second
(`metamorphic.cut(seed, cut_at, resume_at, label)`).

- **The second declaration is compared by role only** (`roles_only`:
  `meta.*` is ignored). An unclosed `{` may legitimately nest it in a block,
  but a keyword must stay a keyword and a name a name.
- **Measure how long it stays broken** with `metamorphic.recovery_summary()`:
  clean, 1 line, 2–5, 6+, or to the end. One broken line right after the cut
  is often unavoidable: after `val x:`, the next word is read as the type.
  The bugs are the ones that never recover.
- **Label cuts by the last token and the open brackets**
  (`cut:after ( open {(`) to see which unfinished constructs leak. In testing,
  the worst were an unclosed parameter list and an unclosed `<`: each turned
  every later declaration in the file into parameters or types. That
  happened on about 5% of cuts in real code. Cuts happen at token
  boundaries, so a string or comment is never left open (that one
  legitimately swallows the rest).

**Skip known limits once they're written down.** When the bugs left are the
ones that can't be fixed (Step 6), they swamp every report: in testing, one
"modifier alone at end of line" limit was 78% of all reflow hits on a corpus.
Give each variant rule a coarse check for those cases, skip matching
variants, and print how many each reason skipped.

## Step 5: Run and read the report

```python
with Dumper(syntax, comment_char) as dumper:
    seeds = [s for s in seeds if dumper.dumpable(s.text)]
    variants = build_variants(seeds)          # yours
    diffs = metamorphic.run(dumper, variants)
    print(metamorphic.report(diffs, len(variants), strip=corpus_dir + "/"))
```

Groups are keyed by scope change (`where`, leaf scope before and after),
not by variant label, so one bug shows up once with every label that hit it.
Context groups come first, each with its shortest example.

## Step 6: Triage

- **A diff only shows that the two versions disagree, not which one is
  wrong.** Dump the original on its own and check it. A reflow hit is often
  a bug in the one-line original (Kotlin: a default value `null` scoped as a
  parameter, a `when` body inside a lambda scoped as a lambda).
- **Check that the variant is still the same program.** Lexer bugs and rules
  that are too broad cause most false positives.
- **Shrink by hand:** dump the snippet from the example, then delete lines
  and tokens while the bad scope stays. Seeds are usually short enough that
  this takes a minute.
- **Put reflow hits in one of two classes:**
  - *A context pops at end of line* although the grammar continues (a type
    after a line-final `:`, supertypes on the next line). These are
    fixable.
  - *The scope depends on a token on the next line* (Kotlin: `fun` ⏎
    `interface`, `name<A,` ⏎ `B>()` as a generic call). Sublime matches one line at a
    time, so these need `branch_point` or can't be fixed. List them as
    known limits.
- **Write each bug down** with a minimal snippet, the wrong scope and the
  expected role. Put them in a BUGS.md, or in tests once fixed: `dump_scopes
  --yaml` gives the starting block. One entry per *bug*, not per group.
  Judge each group by its example, not its count: a real bug in code
  nobody writes isn't worth an entry.

## Step 7: Check fixes with golden dumps

Fixing the bugs from Step 6 changes the syntax, and every change can re-scope
code that no test asserts. Before committing, compare against the last
commit on the same corpus:

```bash
"$SKILL_ROOT/scripts/golden_dumps.py" --syntax X.sublime-syntax -c '//' corpus/
"$SKILL_ROOT/scripts/golden_dumps.py" --syntax X.sublime-syntax -c '//' --base main --all corpus/
```

It dumps every file the syntax claims (its `file_extensions`) with the
package's syntaxes at `--base` (default `HEAD`) and with the working copy,
and groups every run of changed characters by the scopes it lost and gained.
Lines that read as assertions are blanked on both sides, so whole files can
be compared. About 12 s for 115k lines.

- **Grouping ignores `meta.*` when anything else changed.** A new
  `meta.block` appears at every nesting depth and would otherwise split one
  change into a group per depth. Changes only to `meta.*` scopes get their
  own groups.
- **Expect most groups to be the fix itself**, often thousands of runs
  (`meta only: +meta.block`). Read the small groups with odd role changes:
  strings, numbers or brackets losing their scopes, operators changing kind,
  identifiers turning into types. A typed-lambda regression that passed every
  curated test showed up as `-string.quoted.double` and `&&` as a type operator.
- **A change isn't a verdict either way.** A `}` that gains `meta.lambda` can
  be an old leak getting fixed. Look at the example before filing it.
- **Shrink regressions to a test before fixing them**, so the next golden run
  doesn't need to catch them again.

## Further ideas (not tried)

- **Annotations or decorators** added before declarations (`@Suppress("x")`),
  with `replace_gap`. Realistic, and annotation contexts are a common bug source.
- **Realistic whitespace:** tabs instead of spaces for indentation, and
  optional spaces dropped where codebases drop them (`if(x)`, `a+b`, `Map<K,V>`).
- **A coverage report for the test suite:** give a copy of the syntax a marker
  scope per rule, dump the curated tests, and list the rules no test reaches.
- **A differential against a real parser** (tree-sitter, the compiler):
  map its tree to expected roles. It's the only way to catch a role that's wrong
  the same way everywhere, but it's noisy and needs ongoing upkeep.
