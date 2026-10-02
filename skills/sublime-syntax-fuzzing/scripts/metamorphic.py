# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///

# pyright: basic

"""
Language-free core for metamorphic fuzzing of a .sublime-syntax: build
variants of seed sources that must scope the same, dump both with Sublime's
own engine, and report where they don't.

What's language-specific (finding identifiers, choosing where a newline is
allowed) is left to the caller, which passes spans and gaps in.

    import sys; sys.path.insert(0, "<this skill>/scripts")
    from dump_scopes import Dumper
    import metamorphic as mm

    seeds = mm.yaml_seeds("yaml_tests")
    variants = []
    for seed in seeds:
        spans = my_lexer_identifier_spans(seed.text)
        variants.append(mm.alpha_rename(seed, spans, mm.known_words("X.sublime-syntax")))
    with Dumper("X.sublime-syntax", "//") as dumper:
        variants = [v for v in variants if v and dumper.dumpable(v.text) and dumper.dumpable(v.seed.text)]
        print(mm.report(mm.run(dumper, variants), len(variants)))

Needs pyyaml (for known_words and yaml_seeds); declare it in the caller's
PEP 723 header.
"""

import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass

IDENT = re.compile(r"[^\W\d]\w*")


@dataclass
class Seed:
    origin: str  # where it came from, for the report
    text: str  # must end with "\n"; use Seed.make

    @staticmethod
    def make(origin: str, text: str) -> "Seed":
        return Seed(origin, text if text.endswith("\n") else text + "\n")


@dataclass
class Variant:
    seed: Seed
    label: str  # groups are listed by label, e.g. "soft:where", "reflow:after ("
    text: str
    # (orig_start, orig_end, new_start, new_end, kind), covering both texts in
    # order. "same" text is compared character by character, a "renamed" span
    # as a whole against the original's first character, a "gap" not at all.
    segments: list[tuple[int, int, int, int, str]]
    # For a wrapped seed: an offset in text that has the wrapper's scope stack.
    # Seed text is then expected to scope as that stack plus its original
    # stack minus the base scope.
    outer: int | None = None
    # Compare roles only: ignore meta.* scopes (see cut).
    roles_only: bool = False


@dataclass
class Diff:
    variant: Variant
    where: str  # "token": a renamed span; "context": anything else
    orig_off: int
    new_off: int
    before: tuple[str, ...]
    after: tuple[str, ...]
    # roles_only context diffs: the last differing offset in the variant.
    last_new_off: int | None = None


# ---------------------------------------------------------------------------
# Seeds
# ---------------------------------------------------------------------------


def yaml_seeds(tests_dir: str) -> list[Seed]:
    """One seed per block of the YAML test DSL: prefix_lines + line."""
    import yaml

    seeds = []
    for name in sorted(os.listdir(tests_dir)):
        if not name.endswith((".yaml", ".yml")):
            continue
        with open(os.path.join(tests_dir, name), encoding="utf-8") as f:
            data = yaml.safe_load(f)
        for i, block in enumerate(data.get("tests", []), 1):
            lines = list(block.get("prefix_lines", [])) + [block["line"]]
            seeds.append(Seed.make(f"{name}#{i}", "\n".join(lines)))
    return seeds


def known_words(syntax_path: str) -> set[str]:
    """
    Every word in the syntax's variables and match patterns. Renaming one of
    these may legitimately change scopes (a builtin type, `it`, `self`...), so
    don't rename identifiers in this set. Over-inclusive by design: regex
    fragments like `[A-Z]` add A and Z.
    """
    import yaml

    with open(syntax_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    patterns = [v for v in (data.get("variables") or {}).values() if isinstance(v, str)]

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "match" and isinstance(v, str):
                    patterns.append(v)
                else:
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data.get("contexts") or {})
    words = set()
    for p in patterns:
        words.update(IDENT.findall(re.sub(r"\\.", " ", p)))
    return words


# ---------------------------------------------------------------------------
# Variants
# ---------------------------------------------------------------------------


def rename(seed: Seed, spans: list[tuple[int, int]], mapping: dict[str, str], label: str) -> Variant:
    """Replace each span (sorted, non-overlapping) whose text is in mapping."""
    src = seed.text
    out = []
    segments = []
    pos = npos = 0
    for a, b in spans:
        new = mapping.get(src[a:b])
        if new is None:
            continue
        out.append(src[pos:a])
        segments.append((pos, a, npos, npos + a - pos, "same"))
        npos += a - pos
        out.append(new)
        segments.append((a, b, npos, npos + len(new), "renamed"))
        npos += len(new)
        pos = b
    out.append(src[pos:])
    segments.append((pos, len(src), npos, npos + len(src) - pos, "same"))
    return Variant(seed, label, "".join(out), segments)


LETTERS = "qxzjvkwfgbhmpdcnlrstuyaeio"


def respell(name: str, k: int) -> str:
    """
    The k-th fresh spelling of name with the same shape: case per position,
    digits and underscores kept, so capitalisation heuristics see the same thing.
    """
    out = []
    for ch in name:
        if ch.isalpha():
            letter = LETTERS[k % 26]
            k //= 26
            out.append(letter.upper() if ch.isupper() else letter)
        else:
            out.append(ch)
    return "".join(out) + ("q" * k if k else "")


def alpha_rename(seed: Seed, spans: list[tuple[int, int]], known: set[str]) -> Variant | None:
    """Rename every identifier not in known to a fresh one of the same shape."""
    names = {seed.text[a:b] for a, b in spans}
    taken = names | known
    mapping = {}
    for name in sorted(names - known):
        k = 0
        while (new := respell(name, k)) in taken or new == name:
            k += 1
        mapping[name] = new
        taken.add(new)
    return rename(seed, spans, mapping, "alpha") if mapping else None


def replace_gap(seed: Seed, gap_start: int, gap_end: int, text: str, label: str) -> Variant:
    """
    Replace the whitespace in [gap_start, gap_end) (possibly empty) with text,
    which isn't compared: e.g. " /* c */ " between two tokens.
    """
    src = seed.text
    new_end = gap_start + len(text)
    return Variant(
        seed,
        label,
        src[:gap_start] + text + src[gap_end:],
        [
            (0, gap_start, 0, gap_start, "same"),
            (gap_start, gap_end, gap_start, new_end, "gap"),
            (gap_end, len(src), new_end, new_end + len(src) - gap_end, "same"),
        ],
    )


def break_line(seed: Seed, gap_start: int, gap_end: int, label: str, extra_indent: str = "    ") -> Variant:
    """
    Replace the whitespace in [gap_start, gap_end) (possibly empty) with a
    newline indented one level deeper than the current line.
    """
    src = seed.text
    line_start = src.rfind("\n", 0, gap_start) + 1
    indent = re.match(r"[ \t]*", src[line_start:]).group() + extra_indent
    return replace_gap(seed, gap_start, gap_end, "\n" + indent, label)


def cut(seed: Seed, cut_at: int, resume_at: int, label: str, separator: str = "\n\n") -> Variant:
    """
    Code still being typed: drop [cut_at, resume_at) (the rest of a
    declaration) and keep what follows. Only the text after resume_at is
    compared, by role: an unclosed bracket may legitimately nest the rest in
    its meta scopes, but a keyword should stay a keyword.
    """
    src = seed.text
    new_resume = cut_at + len(separator)
    return Variant(
        seed,
        label,
        src[:cut_at] + separator + src[resume_at:],
        [
            (0, cut_at, 0, cut_at, "gap"),
            (cut_at, resume_at, cut_at, new_resume, "gap"),
            (resume_at, len(src), new_resume, new_resume + len(src) - resume_at, "same"),
        ],
        roles_only=True,
    )


def wrap(seed: Seed, header: str, footer: str, label: str, indent: str = "    ") -> Variant:
    """
    Put the seed inside a construct, e.g. header "class W {\n" and footer
    "}\n", indenting every line. Compared as if the wrapper's scopes were
    prepended to the original stacks (see Variant.outer).
    """
    if not header.endswith("\n") or not indent:
        raise ValueError("header must end with a newline, and indent must not be empty")
    src = seed.text
    out = [header]
    segments = [(0, 0, 0, len(header), "gap")]
    npos = len(header)
    pos = 0
    for line in src.splitlines(keepends=True):
        segments.append((pos, pos, npos, npos + len(indent), "gap"))
        npos += len(indent)
        segments.append((pos, pos + len(line), npos, npos + len(line), "same"))
        out += [indent, line]
        npos += len(line)
        pos += len(line)
    segments.append((pos, pos, npos, npos + len(footer), "gap"))
    out.append(footer)
    # The first indent sits in the wrapper's context, before any seed token.
    return Variant(seed, label, "".join(out), segments, outer=len(header))


# ---------------------------------------------------------------------------
# Comparing
# ---------------------------------------------------------------------------


def offset_scopes(text: str, tokens) -> list[tuple[str, ...]]:
    """Scope stack per character offset, from a dump_scopes token list."""
    starts = [0]
    for line in text.split("\n")[:-1]:
        starts.append(starts[-1] + len(line) + 1)
    scopes: list = [None] * len(text)
    for t in tokens:
        base = starts[t.line]
        for c in range(t.start, t.end):
            if base + c < len(text):
                scopes[base + c] = t.scopes
    return scopes


def first_diffs(variant: Variant, orig, new) -> list[Diff]:
    """
    The first difference on a renamed span and, separately, the first one
    anywhere else. Keeping only the first overall would hide every leak behind
    the (often expected) change on the renamed token itself.
    """
    if variant.outer is None:
        expected = orig
    else:
        outer = new[variant.outer]
        expected = [outer + o[1:] for o in orig]
    if variant.roles_only:
        def roles(stack):
            return tuple(sc for sc in stack if not sc.startswith("meta."))

        expected = [roles(o) for o in expected]
        new = [roles(n) for n in new]
    token = context = None
    for oa, ob, na, nb, kind in variant.segments:
        if kind == "renamed" and token is None:
            for k in range(na, nb):
                if new[k] != expected[oa]:
                    token = Diff(variant, "token", oa, k, expected[oa], new[k])
                    break
        elif kind == "same" and context is None:
            for k in range(ob - oa):
                if expected[oa + k] != new[na + k]:
                    context = Diff(variant, "context", oa + k, na + k, expected[oa + k], new[na + k])
                    break
    if context and variant.roles_only:
        oa, ob, na, nb, _ = variant.segments[-1]
        context.last_new_off = max(
            na + k for k in range(ob - oa) if expected[oa + k] != new[na + k]
        )
    return [d for d in (token, context) if d]


def recovery_summary(diffs: list[Diff], variants: list[Variant]) -> str:
    """
    For cut variants: how many lines of the code after the cut stay broken,
    from the first to the last differing line. "never" means the last line of
    the variant still differs.
    """
    buckets = {"clean": 0, "1 line": 0, "2-5 lines": 0, "6+ lines": 0, "never": 0}
    broken = {id(d.variant): d for d in diffs if d.where == "context" and d.last_new_off is not None}
    for v in variants:
        if not v.roles_only:
            continue
        d = broken.get(id(v))
        if d is None:
            buckets["clean"] += 1
            continue
        first = v.text.count("\n", 0, d.new_off)
        last = v.text.count("\n", 0, d.last_new_off)
        if last == v.text.count("\n") - 1:
            buckets["never"] += 1
        else:
            n = last - first + 1
            buckets["1 line" if n == 1 else "2-5 lines" if n <= 5 else "6+ lines"] += 1
    total = sum(buckets.values()) or 1
    return "recovery: " + ", ".join(f"{k} {v} ({100 * v // total}%)" for k, v in buckets.items())


def run(dumper, variants: list[Variant], batch: int = 500, progress: bool = True) -> list[Diff]:
    """
    Dump each seed once and each variant, in batches of one binary run each.
    Filter with dumper.dumpable() first: one undumpable source fails its batch.
    """
    diffs = []
    seed_scopes: dict[int, list] = {}
    for i in range(0, len(variants), batch):
        chunk = variants[i : i + batch]
        new_seeds = {id(v.seed): v.seed for v in chunk if id(v.seed) not in seed_scopes}
        dumps = dumper.dump_many([s.text for s in new_seeds.values()] + [v.text for v in chunk])
        for s, d in zip(new_seeds.values(), dumps):
            seed_scopes[id(s)] = offset_scopes(s.text, d)
        for v, d in zip(chunk, dumps[len(new_seeds) :]):
            diffs.extend(first_diffs(v, seed_scopes[id(v.seed)], offset_scopes(v.text, d)))
        if progress:
            print(f"  {min(i + batch, len(variants))}/{len(variants)}", file=sys.stderr)
    return diffs


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def leaf(scopes: tuple[str, ...]) -> str:
    return scopes[-1] if len(scopes) > 1 else "(base)"


def _show(text: str, off: int) -> list[str]:
    line = text.count("\n", 0, off)
    col = off - (text.rfind("\n", 0, off) + 1)
    lines = text.split("\n")
    out = [f"    {l}" for l in lines[max(0, line - 3) : line + 1]]
    out.append("    " + "".join(c if c == "\t" else " " for c in lines[line][:col]) + "^")
    return out


def report(diffs: list[Diff], total: int, strip: str = "") -> str:
    """
    Group by (where, leaf scope before, leaf scope after), not by variant
    label: one bug usually shows up under many labels. Context groups come
    first, since they point at lookaheads and leaks; each shows its shortest
    example. strip is removed from seed origins (e.g. a corpus path prefix).
    """
    groups: dict[tuple, list[Diff]] = defaultdict(list)
    for d in diffs:
        groups[(d.where, leaf(d.before), leaf(d.after))].append(d)

    changed = len({id(d.variant) for d in diffs})
    out = [f"{changed} of {total} variants changed scopes, in {len(groups)} groups", ""]
    order = sorted(groups.items(), key=lambda kv: (kv[0][0] != "context", -len(kv[1])))
    for (where, before, after), group in order:
        d = min(group, key=lambda d: (len(d.variant.text), d.variant.seed.origin))
        seeds = len({x.variant.seed.origin for x in group})
        labels: dict[str, int] = defaultdict(int)
        for x in group:
            labels[x.variant.label] += 1
        out.append(f"## {where}: {before} -> {after}  ({len(group)} variants, {seeds} seeds)")
        out.append("  variants: " + ", ".join(f"{l} ({n})" for l, n in sorted(labels.items(), key=lambda kv: -kv[1])))
        out.append(f"  example: {d.variant.label}, seed {d.variant.seed.origin.replace(strip, '')}")
        out.append("  before:")
        out.extend(_show(d.variant.seed.text, d.orig_off))
        out.append("  after:")
        out.extend(_show(d.variant.text, d.new_off))
        out.append(f"  before scopes: {' '.join(d.before)}")
        out.append(f"  after scopes:  {' '.join(d.after)}")
        out.append("")
    return "\n".join(out)
