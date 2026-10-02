#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///

# pyright: basic

"""
Show every token a syntax change re-scopes on a corpus.

The same files are dumped with the syntax at a git revision (default HEAD) and
with the working copy, and every run of characters whose scope stack differs
is reported, grouped by which scopes it lost and gained. Catches side effects
that no test asserts.

Usage:
    golden_dumps.py --syntax X.sublime-syntax -c // DIR_OR_FILE...
    golden_dumps.py --syntax X.sublime-syntax -c // --base main --all src/

Directories are searched for the syntax's own file_extensions. Lines that the
syntax_tests binary would read as assertions are blanked on both sides, so
those files are still compared.
"""

import argparse
import os
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dump_scopes import Dumper, reads_as_assertion, split_lines  # noqa: E402


def git(cwd: str, *args: str) -> str:
    proc = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True)
    if proc.returncode:
        sys.exit(f"error: git {' '.join(args)}: {proc.stderr.strip()}")
    return proc.stdout


def checkout_syntaxes(syntax_path: str, rev: str, into: str) -> str:
    """Write the package's .sublime-syntax files at rev into a new dir."""
    syntax_dir = os.path.dirname(os.path.abspath(syntax_path))
    top = git(syntax_dir, "rev-parse", "--show-toplevel").strip()
    rel_dir = os.path.relpath(syntax_dir, top)
    prefix = "" if rel_dir == "." else rel_dir + "/"
    base_dir = os.path.join(into, "base")
    os.makedirs(base_dir)
    for name in git(top, "ls-tree", "--name-only", rev, *([prefix] if prefix else [])).splitlines():
        name = os.path.basename(name)
        if name.endswith(".sublime-syntax"):
            with open(os.path.join(base_dir, name), "w", encoding="utf-8") as f:
                f.write(git(top, "show", f"{rev}:{prefix}{name}"))
    path = os.path.join(base_dir, os.path.basename(syntax_path))
    if not os.path.exists(path):
        sys.exit(f"error: {os.path.basename(syntax_path)} doesn't exist at {rev}")
    return path


def corpus_files(paths: list[str], syntax_path: str) -> list[str]:
    with open(syntax_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    exts = tuple("." + e for e in (data.get("file_extensions") or []) + (data.get("hidden_extensions") or []))
    files = []
    for p in paths:
        if os.path.isdir(p):
            for dirpath, _, names in os.walk(p):
                files.extend(os.path.join(dirpath, n) for n in names if n.endswith(exts))
        else:
            files.append(p)
    return sorted(files)


def read_source(path: str, comment_char: str) -> tuple[str, int]:
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = split_lines(f.read())
    blanked = 0
    for i, line in enumerate(lines):
        if reads_as_assertion(line, comment_char):
            lines[i] = ""
            blanked += 1
    return "\n".join(lines) + "\n", blanked


def dump_all(dumper: Dumper, sources: list[str], batch_lines: int):
    """Per source, a list of lines, each a list of scope stacks per column."""
    out = []
    i = 0
    while i < len(sources):
        j, lines = i, 0
        while j < len(sources) and (j == i or lines + sources[j].count("\n") <= batch_lines):
            lines += sources[j].count("\n")
            j += 1
        for src, tokens in zip(sources[i:j], dumper.dump_many(sources[i:j])):
            cols = [[None] * (len(l) + 1) for l in split_lines(src)]
            for t in tokens:
                for c in range(t.start, t.end):
                    cols[t.line][c] = t.scopes
            out.append(cols)
        print(f"  {j}/{len(sources)}", file=sys.stderr)
        i = j
    return out


def changes(base_cols, new_cols):
    """(line, start, end, before, after) for each run of changed columns."""
    for li, (b_line, n_line) in enumerate(zip(base_cols, new_cols)):
        c = 0
        while c < len(b_line):
            if b_line[c] == n_line[c]:
                c += 1
                continue
            start = c
            while c < len(b_line) and b_line[c] != n_line[c] and (b_line[c], n_line[c]) == (b_line[start], n_line[start]):
                c += 1
            yield li, start, c, b_line[start], n_line[start]


def key(before: tuple[str, ...], after: tuple[str, ...]) -> str:
    """
    The scopes lost and gained, ignoring meta.* when anything else changed: a
    new meta.block shows up at every nesting depth, and would otherwise split
    one change of role into a group per depth. Meta-only changes are keyed by
    the meta scope names, without counts.
    """
    lost = Counter(before) - Counter(after)
    gained = Counter(after) - Counter(before)
    role = [f"-{s}" for s in sorted(lost) if not s.startswith("meta.")]
    role += [f"+{s}" for s in sorted(gained) if not s.startswith("meta.")]
    if role:
        return " ".join(role)
    meta = [f"-{s}" for s in sorted(lost)] + [f"+{s}" for s in sorted(gained)]
    return "meta only: " + (" ".join(meta) or "(reordered)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--syntax", required=True, help="working copy of the .sublime-syntax")
    parser.add_argument("-c", "--comment-char", required=True)
    parser.add_argument("--base", default="HEAD", help="git revision to compare against (default: HEAD)")
    parser.add_argument("--syntax-tests-dir", help="where syntax_tests is installed (default: ./st_syntax_tests)")
    parser.add_argument("--examples", type=int, default=3, help="examples per group")
    parser.add_argument("--all", action="store_true", help="list every changed token instead of grouping")
    parser.add_argument("--batch-lines", type=int, default=20000, help="source lines per syntax_tests run")
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()

    files = corpus_files(args.paths, args.syntax)
    if not files:
        sys.exit("error: no files matched the syntax's file_extensions")
    read = [read_source(f, args.comment_char) for f in files]
    sources = [s for s, _ in read]
    blanked = sum(n for _, n in read)
    total_lines = sum(s.count("\n") for s in sources)
    print(f"{len(files)} files, {total_lines} lines ({blanked} blanked: they read as assertions)", file=sys.stderr)

    print("dumping with the working copy", file=sys.stderr)
    with Dumper(args.syntax, args.comment_char, args.syntax_tests_dir) as dumper:
        new = dump_all(dumper, sources, args.batch_lines)
        package = dumper.package
    # Same package name, so the base replaces the installed syntax instead of
    # being loaded next to it under the same scope.
    with tempfile.TemporaryDirectory(prefix="golden_") as tmp:
        base_syntax = checkout_syntaxes(args.syntax, args.base, tmp)
        print(f"dumping with {args.base}", file=sys.stderr)
        with Dumper(base_syntax, args.comment_char, args.syntax_tests_dir, as_package=package) as dumper:
            base = dump_all(dumper, sources, args.batch_lines)

    root = os.path.commonpath([os.path.abspath(p) for p in args.paths])
    root = root if os.path.isdir(root) else os.path.dirname(root)
    groups: dict[str, list] = defaultdict(list)
    changed_files = set()
    for path, src, b, n in zip(files, sources, base, new):
        lines = split_lines(src)
        rel = os.path.relpath(os.path.abspath(path), root)
        for li, start, end, before, after in changes(b, n):
            text = (lines[li] + "\n")[start:end]
            if args.all:
                print(f"{rel}:{li + 1}:{start}\t{text!r}\t{' '.join(before)}  =>  {' '.join(after)}")
            groups[key(before, after)].append((rel, li, start, end, lines[li], before, after))
            changed_files.add(path)

    runs = sum(len(g) for g in groups.values())
    summary = f"{runs} changed runs in {len(changed_files)} of {len(files)} files, {len(groups)} groups ({args.base} -> working copy)"
    if args.all:
        print(summary, file=sys.stderr)
        return
    print(summary)
    print()
    for k, g in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        print(f"## {k}  ({len(g)} runs, {len({x[0] for x in g})} files)")
        for rel, li, start, end, line, before, after in g[: args.examples]:
            print(f"  {rel}:{li + 1}:{start}")
            print(f"    {line}")
            print("    " + "".join(c if c == "\t" else " " for c in line[:start]) + "^" * max(1, min(end, len(line)) - start))
            print(f"    before: {' '.join(before)}")
            print(f"    after:  {' '.join(after)}")
        print()


if __name__ == "__main__":
    main()
