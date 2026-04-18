**NOTE:** Placeholders are marked with $

Your task is to write a good Sublime Text syntax for $lang.

The syntax is in $pathToSyntax. I have added some scaffolding but other than comments and the shebang there's not much done.

These files will help you do that, read them all:

- support/SUBLIME_SYNTAX_REFERENCE.md: Contains notes on how to define sublime text syntaxes.
- support/SCOPE_NAMING_GUIDELINES.md: Contains notes on how to name the captures outputs following best practices.
- support/SYNTAX_DEVELOPMENT_TIPS.md: Other tips and tricks to keep in mind when developing syntaxes

$ifProvidingAGrammar

- support/plaintext_grammar.txt: Contains the full specification of the $lang grammar. Keep in mind you already know how to write $lang, and a syntax and a grammar are different things. You need to assign scopes to positions, not validate if the user is writing "void" where it shouldn't.

**Testing**

It is IMPERATIVE to have extensive test coverage. Sublime's default syntaxes have coverage for all language features, going from basic uses to complicated edge cases. I expect you to produce similar levels of coverage.

Sublime's syntax tests are very hard to write for LLMs so I am providing you with a wrapper so you can write them in YAML.

You will write tests in YAML format following the example of tests/example.yaml. The tests you write must be YAML and they must be in that tests/ directory.

To run them, you will do `mise run test`.

The output when there are failures relies on vertical alignment to point to the errors, I'm hoping you can follow it okay. Make changes small so you can track what breaks. You won't have access to any other tool to inspect scopes other than these tests. If you're having issues parsing the output, you're better off writing a short python script and parsing the output yourself.

**Troubleshooting**

A common problem with syntaxes written with pushdown automata is getting 'stuck' in a context, and it affecting lines below if the context is not popped.
