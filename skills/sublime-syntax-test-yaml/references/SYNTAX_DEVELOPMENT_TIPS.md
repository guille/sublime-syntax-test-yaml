Syntax Development Tips (summarized)
=================================

Core Concepts and Patterns
--------------------------

Scope Doubling (common pitfall)
- Be careful with `meta_scope` and punctuation; parentheses/braces/brackets can easily get doubled scopes.
- Add tests that assert the exact scope sequence (e.g. `^ punctuation` and `^ - punctuation punctuation`).

Stateful Chaining: Push vs Set
- Keep `main` stateless. Use `push` to enter a multi-token sequence and `pop` when finished.
- `set` replaces the top of the stack and is useful for single-state transitions, but chaining many `set`s is harder to reason about.
- Prefer pushing a context that contains a `meta_scope` and subsequent consuming rules.

Lookahead Push for Meta-Scoping
- When you want a `meta_scope` around a multi-token chunk, use a non-consuming lookahead to `push` the state:

```yaml
 - match: (?=a)
   push: expect-a

expect-a:
 - meta_scope: meta.abc
 - match: a
   scope: first
   set: expect-b
```

Bail-Outs (force-safe behavior while editing)
- Provide a bail-out (lookahead-pop) in every stateful context. Always provide ways to bail out of mid-state contexts so partial typing doesn't corrupt later scoping.
- Common patterns:
  - else-pop (pop when non-whitespace follows):

```yaml
else-pop:
 - match: (?=\S)
   pop: true
```

  - force-pop (immediate pop):

```yaml
force-pop:
 - match: ''
   pop: true
```

  - eol-pop (pop at end of line):

```yaml
eol-pop:
 - match: '$'
   pop: true
```

These are useful to prevent contexts from hanging when optional parts are omitted.

Stacking Contexts (put several contexts on the stack at once)
- For predictable sequences (like function body -> closing brace -> statements), push a list of contexts so the stack unwinds naturally as tokens are matched.
- Example:

```yaml
function-body:
 - match: \{
   scope: punctuation.section.braces.begin
   set:
     - meta-function-body
     - expect-closing-brace
     - statements
     - directives
```

Preprocessing & YAML Macros (DRY)
- Use a build-time YAML preprocessor to implement macros for common patterns (keywords, identifier variants, meta wrappers).
- Example macros: `!word` to emit `(?i)\b(?:...)\b`, `!expect_identifier` to handle quoted/unquoted identifiers and pop rules.

Keep Matches Concise (important for embedding)
- Avoid `.*` or consuming whole-line patterns. Instead:
  - Match only the marker (e.g. `//`) and `push` a `meta_scope` with a rule to consume EOL.
  - This allows `with_prototype` and embedding syntax to interrupt correctly.

Example (line comment handling):

```yaml
comments:
 - match: '//'
   scope: punctuation.definition.comment
   push:
     - meta_scope: comment.line
     - match: $\n?
       pop: true
```

Regex Flags and Variable Hygiene
- When enabling flags in variables, use scoped inline flags: `(?x: ... )` or `(?i: ... )` instead of global `(?x)` to avoid leaking flags beyond the variable.
- Make variables atomic by wrapping them in a non-capturing group: `example_var: (?:\w+[.:])` so `{{var}}{2}` behaves predictably.
- When using YAML block scalars for big regexes, use the chomping indicator `|-` to remove the trailing newline.

Rule Loop & Matching Behavior
- When a rule matches, the rule loop restarts from the first rule. Only zero-width matches (lookaheads, `''`, `$`) advance the loop without consuming characters.
- Be careful with ordering: rules behave differently when they consume vs do not consume characters.
- At EOL, the engine runs the loop again against a special EOL position; non-consuming matches may interact unexpectedly with the next rules.

Naming & Organization
- Use plural names for non-popping (looping) contexts, singular for single-match/popping contexts (e.g. `strings` vs `string-content`).
- Prefer named contexts: they are easier to override/extend when a syntax is inherited.
- Use variables for large token lists (keywords, builtins); this keeps contexts readable and easier to override.
