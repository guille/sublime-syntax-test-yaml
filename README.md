# Sublime Text syntax tests AI helper

These are some helper items I used for https://github.com/guille/sublime-dart/. Keeping them here in case someone else finds them useful, or I want to use them again in the future.

This includes barely-edited versions of the AGENTS.md and the mise.toml I used.

## Writing tests and reading results

Sublime Text's syntax tests are very easy to read and write (if a bit cumbersome) for humans, but LLMs are awful at positional counting and vertical relationships.

I wanted an LLM to write a sublime syntax for me. Since LLM performance improves when they have a loop by which they can check their work. I set up the [syntax test](https://github.com/sublimetext/syntax-test-action) binary locally, but quickly found GPT-5.4 was terrible at writing tests or interpreting failures.

This repo has two Python wrapper scripts that help our favourite overcaffeinated stochastic goblins do the work properly:
- yaml2syntaxtest.py: Allows writing syntax tests in YAML.
- parse_syntax_test.py: Transform the syntax test failure output into a machine-readable strings.

I have only tried one version of the syntax test binary (ST4200). The code is also completely AI-generated, minus one off-by-one error that I fixed by hand. It's a mess, don't even look.

## Syntax writing skills

The `suppport/` dir has some LLM-generated summaries of these three sites, fetched in April 2026:
1. https://www.sublimetext.com/docs/syntax.html
2. https://www.sublimetext.com/docs/scope_naming.html
3. https://github.com/sublimehq/Packages/issues/757

Feeding them to the LLM seems to improve results.
