#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pyyaml",
# ]
# ///

# pyright: basic

"""
Convert a YAML syntax test DSL to Sublime Text .sublime-syntax-test format.

YAML structure:
  syntax: "Packages/RSpec/RSpec.sublime-syntax"    # required
  comment_char: "#"                                # optional, default "#"
  tests:
    - line: "describe Some::Tag do"
      assertions:
        # Joined with "&": all must be present, in any nesting order. A space
        # would instead mean "nested inside", and a comma would mean OR.
        - span: "describe"
          scopes: [keyword.other.rspec.behaviour, meta.rspec.behaviour]
          nth: 0                                   # optional, 0-indexed, default 0
        # Use a single string for subtraction, or a deliberate nesting path:
        - span: "describe"
          scopes: ["keyword.other.rspec.behaviour - comment"]
        - span: "Some::Tag do"
          scopes: [meta.rspec.behaviour]
    - prefix_lines:                                # optional consecutive lines
        - "foo = bar \\"                           # emitted verbatim, no blank
      line: "    baz"                              # between them and `line`
      assertions:
        - span: "baz"
          scopes: [meta.continuation]

Usage:
  python yaml2syntaxtest.py input.yaml                        # prints to stdout
  python yaml2syntaxtest.py input.yaml output.rb              # writes to file output.rb
  python yaml2syntaxtest.py input_dir output_dir              # processes every yaml file

In directory mode a `.comment_chars.json` manifest is written alongside the
generated tests, mapping each generated file to the comment character it was
written with, for parse_syntax_test.py --comment-map. Any file that fails to
convert is reported on stderr and makes the whole run exit non-zero.
"""

import json
import os
import sys
import textwrap

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

# Kept in sync by hand with parse_syntax_test.py — the two are standalone uv
# scripts and can't import each other.
COMMENT_MAP_NAME = ".comment_chars.json"


def comment_map_path(output_dir: str) -> str:
    return os.path.join(output_dir, COMMENT_MAP_NAME)


def find_span(line: str, span: str, nth: int = 0):
    """Return (start, end) of the nth occurrence of span in line, or None."""
    start = 0
    for _ in range(nth + 1):
        idx = line.find(span, start)
        if idx == -1:
            return None
        found_start = idx
        start = idx + 1
    return (found_start, found_start + len(span))


def assertion_lines(
    comment_char: str, col_start: int, col_end: int, scopes: list[str]
) -> list[str]:
    """
    Return one or more assertion lines covering [col_start, col_end).

    Columns 0..len(comment_char)-1 are "shadowed" — a normal caret line would
    require placing a ^ inside or immediately colliding with the comment marker.
    For those columns we emit a <- line instead, indenting the comment marker to
    sit directly above the column it needs to test:

        col 0:  <comment_char> <- <scopes>
        col 1:  ' ' <comment_char> <- <scopes>
        ...

    For columns >= len(comment_char) we emit one ordinary caret line:

        <comment_char><padding><^^^...> <scopes>

    where padding aligns the first ^ over col_start (or the first col past the
    shadowed zone, whichever is greater).
    """
    cc_len = len(comment_char)
    # "&" not " ": space is a nesting path (outer to inner), so a correct set of
    # scopes listed in the wrong order fails. "&" is order-independent AND.
    scope_str = " & ".join(scopes)
    lines = []

    # One <- line per shadowed column that falls inside the span
    for col in range(col_start, min(col_end, cc_len)):
        lines.append(" " * col + comment_char + " <- " + scope_str)

    # One caret line for the unshadowed remainder of the span (if any)
    caret_start = max(col_start, cc_len)
    if caret_start < col_end:
        padding = " " * (caret_start - cc_len)
        carets = "^" * (col_end - caret_start)
        lines.append(f"{comment_char}{padding}{carets} {scope_str}")

    return lines


# ---------------------------------------------------------------------------
# Converter
# ---------------------------------------------------------------------------


def convert(yaml_text: str) -> tuple[str, str]:
    """Return (generated test file contents, comment char it was written with)."""
    data = yaml.safe_load(yaml_text)

    # --- header fields ---
    syntax = data.get("syntax")
    comment = data.get("comment_char", "#")

    if not syntax:
        raise ValueError(
            "YAML must include a 'syntax' field (e.g. Packages/Ruby/Ruby.sublime-syntax)"
        )
    out = []
    out.append(f'{comment} SYNTAX TEST "{syntax}"')
    out.append("")

    # --- test blocks ---
    for block_idx, block in enumerate(data.get("tests", []), 1):
        source = block.get("line", "")
        if not isinstance(source, str):
            raise ValueError(f"Block {block_idx}: 'line' must be a string")

        # Optional consecutive physical lines emitted verbatim immediately
        # before `line`, with no blank or assertion lines in between. This lets
        # a test exercise constructs that depend on the preceding lines being
        # contiguous (e.g. backslash line continuations, which a blank line
        # would terminate). Assertions still apply only to `line`.
        prefix_lines = block.get("prefix_lines", [])
        if not isinstance(prefix_lines, list):
            raise ValueError(f"Block {block_idx}: 'prefix_lines' must be a list")
        for pl in prefix_lines:
            if not isinstance(pl, str):
                raise ValueError(
                    f"Block {block_idx}: each 'prefix_lines' item must be a string"
                )
            out.append(pl)

        out.append(source)

        for assert_idx, assertion in enumerate(block.get("assertions", []), 1):
            span = assertion.get("span")
            scopes = assertion.get("scopes", [])
            nth = assertion.get("nth", 0)

            if span is None:
                raise ValueError(
                    f"Block {block_idx}, assertion {assert_idx}: missing 'span'"
                )
            if not scopes:
                raise ValueError(
                    f"Block {block_idx}, assertion {assert_idx}: 'scopes' is empty"
                )
            if isinstance(scopes, str):
                scopes = [scopes]

            result = find_span(source, span, nth)
            if result is None:
                occurrence = f"occurrence #{nth}" if nth else "first occurrence"
                raise ValueError(
                    f"Block {block_idx}, assertion {assert_idx}: "
                    f"span {span!r} ({occurrence}) not found in line:\n  {source!r}"
                )

            col_start, col_end = result
            out.extend(assertion_lines(comment, col_start, col_end, scopes))

        out.append("")

    return "\n".join(out), comment


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(
            textwrap.dedent("""\
            Usage:
              yaml2syntaxtest.py <input.yaml>              # print to stdout
              yaml2syntaxtest.py <input.yaml> <output.rb>  # write to file
              yaml2syntaxtest.py <input_dir> <output_dir>  # process all yaml files
        """)
        )
        sys.exit(0 if sys.argv[1:] else 1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) >= 3 else None

    input_is_dir = os.path.isdir(input_path)
    output_is_dir = os.path.dirname(output_path) if output_path else None

    if input_is_dir:
        if not output_path:
            sys.exit("Error: output directory required when input is a directory")
        os.makedirs(output_path, exist_ok=True)

        import glob as glob_module

        yaml_files = glob_module.glob(
            os.path.join(input_path, "*.yaml")
        ) + glob_module.glob(os.path.join(input_path, "*.yml"))

        if not yaml_files:
            sys.exit(f"Error: no .yaml or .yml files found in {input_path}")

        comment_chars = {}
        errors = 0

        for yaml_file in sorted(yaml_files):
            try:
                with open(yaml_file, encoding="utf-8") as f:
                    yaml_text = f.read()
            except OSError as exc:
                print(f"Error reading {yaml_file}: {exc}", file=sys.stderr)
                errors += 1
                continue

            try:
                result, comment = convert(yaml_text)
            except (ValueError, yaml.YAMLError) as exc:
                print(f"Error processing {yaml_file}: {exc}", file=sys.stderr)
                errors += 1
                continue

            basename = os.path.splitext(os.path.basename(yaml_file))[0]
            out_name = f"syntax_test_{basename}"
            out_file = os.path.join(output_path, out_name)
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(result)
            comment_chars[out_name] = comment
            print(f"Written to {out_file}")

        # Consumed by parse_syntax_test.py --comment-map, so failures in files
        # using different comment characters can be parsed in a single run.
        with open(comment_map_path(output_path), "w", encoding="utf-8") as f:
            json.dump(comment_chars, f, indent=2, sort_keys=True)

        if errors:
            # Exiting non-zero matters: a silently skipped test file would
            # otherwise let the whole suite report green.
            sys.exit(f"Error: {errors} of {len(yaml_files)} test file(s) failed to convert")
        sys.exit(0)

    try:
        with open(input_path, encoding="utf-8") as f:
            yaml_text = f.read()
    except FileNotFoundError:
        sys.exit(f"Error: file not found: {input_path}")

    try:
        result, _ = convert(yaml_text)
    except (ValueError, yaml.YAMLError) as exc:
        sys.exit(f"Error: {exc}")

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"Written to {output_path}")
    else:
        print(result)


if __name__ == "__main__":
    main()
