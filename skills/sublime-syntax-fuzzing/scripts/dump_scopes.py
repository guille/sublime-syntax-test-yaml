#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///

# pyright: basic

"""
Dump the scopes Sublime's own syntax_tests binary assigns to source code.

Every column of every source line, newline included, gets an assertion that
can never match. The binary then reports the actual scope stack of each token,
which is parsed back into (line, start, end, scopes) runs. Columns count code
points.

All inputs of one call run in a single binary invocation, inside a private
copy of the binary's data directory, so the package's own tests don't run and
nothing under the real Data/ is touched.

Usage:
    dump_scopes.py --syntax Kotlin.sublime-syntax --comment-char // FILE...
    dump_scopes.py --syntax Kotlin.sublime-syntax -c // --json FILE
    dump_scopes.py --syntax Kotlin.sublime-syntax -c // --yaml [--line N] FILE

FILE may be "-" for stdin.

The comment char is the token the generated test file uses for its
assertions, so it must start a line comment in the syntax: the assertion
lines are part of the buffer being scoped. A source line that the binary
would itself read as an assertion with that token (see reads_as_assertion)
can't be dumped; Dumper.dumpable() checks for one.

--yaml prints a test block for the YAML test DSL: line N (default: the last
one) with every non-whitespace token asserted, and the lines before it as
prefix_lines. Lines after N are dropped, since they can't affect its scopes.

As a library:
    with Dumper("Kotlin.sublime-syntax", "//") as d:
        tokens_per_source = d.dump_many([src1, src2])
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass

HEADER_RE = re.compile(r"^(.+?):(\d+):(\d+)$")
SEGMENT_RE = re.compile(r"^( *)(\^+)\s+(.*?)\s*$")
BOGUS_SCOPE = "zz.dump.never-matches"
TEST_PREFIX = "syntax_test_dump_"


@dataclass(frozen=True)
class Token:
    line: int  # 0-indexed line of the source
    start: int  # code point columns, end exclusive
    end: int  # end == len(line) + 1 when the run includes the newline
    scopes: tuple[str, ...]


def reads_as_assertion(line: str, comment_char: str) -> bool:
    """
    Whether the binary takes a source line for an assertion: the test file's
    comment token (not the language's, if it has several) after optional
    whitespace, then ^, <- or @ (a symbol assertion) after optional whitespace.
    With "//", `//@Warmup(x)` and `  // ^ x` are assertions but `/// ^`,
    `// x ^` and `#^` are not; with "#", `//@Warmup(x)` is plain source.
    """
    return re.match(rf"\s*{re.escape(comment_char)}\s*(\^|<-|@)", line) is not None


def split_lines(source: str) -> list[str]:
    lines = source.split("\n")
    if len(lines) > 1 and lines[-1] == "":
        lines.pop()
    return lines


class Dumper:
    def __init__(
        self,
        syntax_path: str,
        comment_char: str,
        syntax_tests_dir: str | None = None,
        as_package: str | None = None,
    ):
        """
        as_package dumps the .sublime-syntax files next to syntax_path as that
        package, in place of the installed package's own syntax files: e.g. an
        older revision of an installed syntax, without both being loaded.
        """
        self.syntax_path = os.path.abspath(syntax_path)
        self.as_package = as_package
        self.comment_char = comment_char
        self.syntax_tests_dir = os.path.abspath(
            syntax_tests_dir or os.environ.get("SYNTAX_TESTS_DIR", "st_syntax_tests")
        )
        self._root = None

    def __enter__(self):
        binary = os.path.join(self.syntax_tests_dir, "syntax_tests")
        if not os.access(binary, os.X_OK):
            raise FileNotFoundError(f"syntax_tests binary not found at {binary}")

        # The binary looks for Data/ next to its own executable, so it needs a copy.
        self._root = tempfile.mkdtemp(prefix="dump_scopes_")
        shutil.copy2(binary, self._root)
        packages = os.path.join(self._root, "Data", "Packages")

        # Mirror every installed package so `extends` and `embed` across
        # packages resolve, but leave out their tests: the binary runs every
        # test file it finds under Packages/.
        os.makedirs(packages)
        real_packages = os.path.join(self.syntax_tests_dir, "Data", "Packages")
        syntax_real = os.path.realpath(self.syntax_path)
        as_package = self.as_package
        self.package = as_package
        for pkg in sorted(os.listdir(real_packages)) if os.path.isdir(real_packages) else []:
            src = os.path.join(real_packages, pkg)
            if not os.path.isdir(src):
                continue
            os.makedirs(os.path.join(packages, pkg))
            for name in os.listdir(src):
                entry = os.path.join(src, name)
                if name == "tests" or name.startswith("syntax_test_"):
                    continue
                if pkg == as_package and name.endswith(".sublime-syntax"):
                    continue
                if as_package is None and os.path.realpath(entry) == syntax_real:
                    self.package = pkg
                os.symlink(os.path.realpath(entry), os.path.join(packages, pkg, name))

        # Not linked by the test skill's setup (or replacing it): use the
        # syntax's own directory, named after it unless as_package says otherwise.
        if self.package is None or as_package is not None:
            syntax_dir = os.path.dirname(self.syntax_path)
            self.package = as_package or os.path.basename(syntax_dir)
            os.makedirs(os.path.join(packages, self.package), exist_ok=True)
            for name in os.listdir(syntax_dir):
                link = os.path.join(packages, self.package, name)
                if name.endswith(".sublime-syntax") and not os.path.lexists(link):
                    os.symlink(os.path.join(syntax_dir, name), link)
        self._package_dir = os.path.join(packages, self.package)
        return self

    def __exit__(self, *exc):
        shutil.rmtree(self._root, ignore_errors=True)

    def dumpable(self, source: str) -> bool:
        """False if a line would be read as an assertion, which can't be dumped."""
        return not any(reads_as_assertion(line, self.comment_char) for line in split_lines(source))

    def dump(self, source: str) -> list[Token]:
        return self.dump_many([source])[0]

    def dump_many(self, sources: list[str]) -> list[list[Token]]:
        if self._root is None:
            raise RuntimeError("Dumper must be used as a context manager")

        for name in os.listdir(self._package_dir):
            if name.startswith(TEST_PREFIX):
                os.remove(os.path.join(self._package_dir, name))

        # test file name -> {test file line number: source line index}
        line_maps = {}
        all_lines = []
        for i, source in enumerate(sources):
            name = f"{TEST_PREFIX}{i:06d}"
            lines = split_lines(source)
            all_lines.append(lines)
            content, line_maps[name] = self._test_file(lines, i)
            with open(os.path.join(self._package_dir, name), "w", encoding="utf-8") as f:
                f.write(content)

        proc = subprocess.run(
            [os.path.join(self._root, "syntax_tests")],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        output = proc.stdout + proc.stderr

        # source index -> line index -> column -> scopes
        columns: list[list[dict[int, tuple[str, ...]]]] = [
            [{} for _ in lines] for lines in all_lines
        ]
        for name, test_line, segments in parse_output(output):
            src_line = line_maps.get(name, {}).get(test_line)
            if src_line is None:
                continue
            idx = int(name[len(TEST_PREFIX):])
            newline_col = len(all_lines[idx][src_line])
            cols = columns[idx][src_line]
            for start, end, scopes in segments:
                # Reported tokens are whole, even past the asserted columns.
                for c in range(start, min(end, newline_col + 1)):
                    cols[c] = scopes

        result = []
        for idx, lines in enumerate(all_lines):
            tokens = []
            for li, line in enumerate(lines):
                cols = columns[idx][li]
                missing = [c for c in range(len(line) + 1) if c not in cols]
                if missing:
                    raise RuntimeError(
                        f"source {idx} line {li + 1}: no scopes reported for columns "
                        f"{missing[:5]}{'...' if len(missing) > 5 else ''}\n"
                        f"binary output (truncated):\n{output[:2000]}"
                    )
                tokens.extend(runs(li, cols, len(line) + 1))
            result.append(tokens)
        return result

    def _test_file(self, lines: list[str], idx: int) -> tuple[str, dict[int, int]]:
        cc = self.comment_char
        out = [f'{cc} SYNTAX TEST "Packages/{self.package}/{os.path.basename(self.syntax_path)}"']
        line_map = {}
        for li, line in enumerate(lines):
            if reads_as_assertion(line, cc):
                raise ValueError(
                    f"source {idx} line {li + 1} would be read as an assertion with "
                    f"comment char {cc!r}: {line!r}"
                )
            out.append(line)
            line_map[len(out)] = li
            # Columns 0..len(line), the last one being the newline; carets past
            # it would spill into the next line. The first
            # len(cc) columns sit under the comment token, so they need <- lines.
            # Their indent must repeat the source's leading tabs, or the binary
            # rejects the file for mismatched whitespace.
            last = len(line)
            for col in range(min(last + 1, len(cc))):
                indent = "".join(ch if ch == "\t" else " " for ch in line[:col])
                out.append(f"{indent}{cc} <- {BOGUS_SCOPE}")
            if last >= len(cc):
                out.append(f"{cc}{'^' * (last + 1 - len(cc))} {BOGUS_SCOPE}")
        return "\n".join(out) + "\n", line_map


def parse_output(output: str):
    """Yield (test file name, test file line, [(start, end, scopes)]) per failure."""
    lines = output.split("\n")
    i = 0
    while i < len(lines):
        header = HEADER_RE.match(lines[i].strip())
        i += 1
        if not header:
            continue
        segments = []
        in_actual = False
        while i < len(lines) and lines[i].strip():
            line = lines[i]
            i += 1
            if line.strip() == "actual:":
                in_actual = True
            elif in_actual and " | " in line:
                # Carets are aligned to the text after the gutter, whose width
                # depends on the line number.
                m = SEGMENT_RE.match(line.split(" | ", 1)[1])
                if m:
                    start = len(m.group(1))
                    segments.append(
                        (start, start + len(m.group(2)), tuple(m.group(3).split()))
                    )
        yield os.path.basename(header.group(1)), int(header.group(2)), segments


def runs(line: int, cols: dict[int, tuple[str, ...]], width: int) -> list[Token]:
    tokens = []
    start = 0
    for c in range(1, width + 1):
        if c == width or cols[c] != cols[start]:
            tokens.append(Token(line, start, c, cols[start]))
            start = c
    return tokens


def find_nth(line: str, span: str, start: int) -> int:
    """The `nth` the YAML DSL needs to find span at start (it steps by one)."""
    nth = 0
    idx = line.find(span)
    while idx != start:
        nth += 1
        idx = line.find(span, idx + 1)
    return nth


def yaml_block(lines: list[str], tokens: list[Token], target: int) -> str:
    def q(s):
        return json.dumps(s, ensure_ascii=False)

    line = lines[target]
    out = []
    if target > 0:
        out.append("  - prefix_lines:")
        out.extend(f"      - {q(pl)}" for pl in lines[:target])
        out.append(f"    line: {q(line)}")
    else:
        out.append(f"  - line: {q(line)}")
    out.append("    assertions:")
    for t in tokens:
        if t.line != target:
            continue
        text = line[t.start : min(t.end, len(line))]
        stripped = text.strip()
        if not stripped:
            continue
        start = t.start + (len(text) - len(text.lstrip()))
        scopes = t.scopes[1:] or t.scopes
        out.append(f"      - span: {q(stripped)}")
        nth = find_nth(line, stripped, start)
        if nth:
            out.append(f"        nth: {nth}")
        out.append(f"        scopes: [{', '.join(scopes)}]")
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(description="Dump scopes via Sublime's syntax_tests binary")
    parser.add_argument("--syntax", required=True, help="path to the .sublime-syntax file")
    parser.add_argument("-c", "--comment-char", required=True, help="line comment token, e.g. //")
    parser.add_argument("--syntax-tests-dir", help="where syntax_tests is installed (default: ./st_syntax_tests, env SYNTAX_TESTS_DIR)")
    fmt = parser.add_mutually_exclusive_group()
    fmt.add_argument("--json", action="store_true", help="print tokens as JSON")
    fmt.add_argument("--yaml", action="store_true", help="print a YAML test block for one line")
    parser.add_argument("--line", type=int, help="with --yaml: 1-indexed line to assert (default: last)")
    parser.add_argument("files", nargs="+")
    args = parser.parse_args()

    if args.yaml and len(args.files) != 1:
        parser.error("--yaml takes exactly one file")
    if args.line is not None and not args.yaml:
        parser.error("--line only applies to --yaml")

    sources = []
    for path in args.files:
        if path == "-":
            sources.append(sys.stdin.read())
        else:
            with open(path, encoding="utf-8") as f:
                sources.append(f.read())

    if args.yaml:
        lines = split_lines(sources[0])
        target = (args.line or len(lines)) - 1
        if not 0 <= target < len(lines):
            parser.error(f"--line must be between 1 and {len(lines)}")
        if not lines[target].strip():
            parser.error(f"line {target + 1} is blank, nothing to assert")
        sources[0] = "\n".join(lines[: target + 1]) + "\n"

    with Dumper(args.syntax, args.comment_char, args.syntax_tests_dir) as dumper:
        try:
            dumps = dumper.dump_many(sources)
        except ValueError as e:
            sys.exit(f"error: {e}")

    if args.yaml:
        print(yaml_block(split_lines(sources[0]), dumps[0], target))
    elif args.json:
        out = [
            {"file": path, "tokens": [asdict(t) for t in tokens]}
            for path, tokens in zip(args.files, dumps)
        ]
        json.dump(out, sys.stdout, ensure_ascii=False)
        print()
    else:
        for path, source, tokens in zip(args.files, sources, dumps):
            if len(args.files) > 1:
                print(f"== {path}")
            lines = split_lines(source)
            for t in tokens:
                text = (lines[t.line] + "\n")[t.start : t.end]
                print(f"{t.line + 1}:{t.start}-{t.end}\t{text!r}\t{' '.join(t.scopes)}")


if __name__ == "__main__":
    main()
