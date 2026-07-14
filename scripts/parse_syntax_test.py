#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///

# pyright: basic

"""
Parse Sublime Text syntax test output into an LLM-friendly format.

Usage:
    cat output.log | parse_syntax_test.py
    parse_syntax_test.py < output.log
    cat output.log | parse_syntax_test.py -c "//"

Options:
    -c, --comment-char  Comment character used in syntax tests (default: #)

Output format:
    For each failure:
    - File under test: "..."
    - Text of line under test: "..."
    - Span under test: "..."
    - Expected scope(s): "..."
    - Got scope(s): "..."
"""

import sys
import re


def parse_test_output(output: str, comment_char: str = "#") -> list[dict]:
    failures = []
    lines = output.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"^(.+?):(\d+):(\d+)$", line.strip()):
            block_lines = [line]
            i += 1
            while i < len(lines) and lines[i].strip() != "":
                block_lines.append(lines[i])
                i += 1

            failure = parse_failure_line(block_lines, comment_char)
            if failure:
                failures.append(failure)
        else:
            i += 1

    return failures


def parse_failure_line(lines: list[str], comment_char: str = "#") -> dict | None:
    if len(lines) < 4:
        return None

    result = {}

    first_line = lines[0].strip()
    match = re.match(r"^(.+?):(\d+):(\d+)$", first_line)
    if not match:
        return None

    result["file_under_test"] = match.group(1)
    result["line_under_test"] = int(match.group(2))
    result["column_under_test"] = int(match.group(3))

    source_line = None
    expected_caret_line = None
    actual_start = None
    actual_lines = []

    for i, line in enumerate(lines):
        if " | " in line:
            parts = line.split(" | ", 1)
            if len(parts) < 2:
                continue
            left = parts[0]
            right = parts[1]

            if left.strip().isdigit():
                if right.strip().startswith(comment_char):
                    expected_caret_line = line
                else:
                    source_line = right.strip()

        if line.strip() == "actual:":
            actual_start = i + 1
            continue

        if actual_start and i >= actual_start:
            if not line.strip():
                break
            if " | " in line:
                actual_lines.append(line)

    if source_line:
        result["text_of_line"] = source_line

    span_text = ""
    expected_scopes = ""
    caret_len = 1
    is_arrow = False

    if expected_caret_line:
        parts = expected_caret_line.split(" | ", 1)
        if len(parts) >= 2:
            expected_part = parts[1].strip()

            arrow_match = re.match(
                rf"{re.escape(comment_char)}(\s*)<-\s+(.+)$", expected_part
            )

            if arrow_match:
                padding = len(arrow_match.group(1))
                caret_len = 1
                expected_scopes = arrow_match.group(2).strip()
                is_arrow = True
                arrow_col = padding + 1
                result["arrow_column"] = arrow_col
            else:
                expected_match = re.match(
                    rf"{re.escape(comment_char)}(\s*)(\^*)\s+(.+)$", expected_part
                )
                if expected_match:
                    padding = len(expected_match.group(1))
                    caret_len = len(expected_match.group(2))
                    expected_scopes = expected_match.group(3).strip()

    col = result.get("column_under_test", 0)
    text_of_line = result.get("text_of_line", "")
    source_col = col - 1
    span_text = (
        text_of_line[source_col : source_col + caret_len]
        if 0 <= source_col and source_col + caret_len <= len(text_of_line)
        else ""
    )

    result["span_under_test"] = span_text
    result["expected_scopes"] = expected_scopes

    got_scope = ""
    col = result.get("column_under_test", 0)

    for act_line in actual_lines:
        if " | " not in act_line:
            continue
        idx = act_line.find(" | ")
        if idx == -1:
            continue
        left_spaces = len(act_line[:idx])
        right = act_line[idx + 3 :]

        caret_match = re.match(r"^(\s*)(\^*)\s*(.*)$", right)
        if caret_match:
            right_padding = len(caret_match.group(1))
            act_start = left_spaces + right_padding
            act_len = len(caret_match.group(2))
            act_scope = caret_match.group(3).strip()

            for check_col in [col - 1, col, col + 1]:
                if act_start <= check_col < act_start + act_len:
                    got_scope = act_scope
                    break
            if got_scope:
                break

    result["got_scopes"] = got_scope

    return result


def format_for_llm(failure: dict) -> str:
    lines = []
    lines.append(f'- File under test: "{failure.get("file_under_test", "")}"')
    lines.append(f'- Text of line under test: "{failure.get("text_of_line", "")}"')
    lines.append(f'- Span under test: "{failure.get("span_under_test", "")}"')
    lines.append(
        f'- Text that did not match (expected scope): "{failure.get("expected_scopes", "")}"'
    )
    lines.append(f'- Got scope(s): "{failure.get("got_scopes", "")}"')
    return "\n".join(lines)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Parse Sublime Text syntax test output into LLM-friendly format"
    )
    parser.add_argument(
        "-c",
        "--comment-char",
        default="#",
        help="Comment character used in syntax tests (default: #)",
    )
    args = parser.parse_args()

    output = sys.stdin.read()

    failures = parse_test_output(output, args.comment_char)

    if not failures:
        print("No failures detected.")
        return

    for i, failure in enumerate(failures, 1):
        if i > 1:
            print("\n" + "=" * 40 + "\n")
        print(format_for_llm(failure))

    print(f"\n--- Summary: {len(failures)} failure(s) detected ---")


if __name__ == "__main__":
    main()
