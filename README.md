# Sublime Text syntax tests AI harness

_This file, along with the LICENSE, is the only non-AI-generated file in the repo_.

## Background

I got frustrated because none of the available syntaxes for Dart were high-quality. I am not very good at thinking like a pushdown automata, so I decided to try and have the LLM write the syntax.

The result was pretty bad. LLM performance improves when they can check their own work, and despite setting up the [syntax test](https://github.com/sublimetext/syntax-test-action) binary locally, I quickly found that GPT-5.4 was terrible at writing tests or interpreting failures.

Sublime Text's syntax tests are very easy to read and write (if a bit cumbersome) for humans, but LLMs are awful at positional counting and vertical relationships, it turns out.

As a way to get around this I had the AI write two scripts that help our favourite overcaffeinated stochastic goblins do the work properly:
- yaml2syntaxtest.py: Allows writing syntax tests in YAML.
- parse_syntax_test.py: Transform the syntax test failure output into a machine-readable strings.

Moreover, the `references/` dir has some LLM-generated summaries of these three sites, fetched in April 2026:

1. https://www.sublimetext.com/docs/syntax.html
2. https://www.sublimetext.com/docs/scope_naming.html
3. https://github.com/sublimehq/Packages/issues/757

Feeding them to the LLM seems to improve results.

## Using the repo

I've been copy-pasting these scripts and the `references/` directory into the projects where I use them, but I hear [SKILLs](https://agentskills.io) are all the rage, so I had yet another LLM set that up. I have no clue how to install them, but maybe you will. Or you can just ask whatever bot you're using.

Note the Python scripts require [uv](https://astral.sh/uv).

## Disclaimers

Beyond the usual all-caps disclaimer in the LICENSE, note that I have only tried one version of the syntax test binary (ST4200). The code is also completely AI-generated, minus one off-by-one error that I fixed by hand. It's a mess, don't even look.
