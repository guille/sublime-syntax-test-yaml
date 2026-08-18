#!/usr/bin/env bash
# Generate .sublime-syntax-test files from YAML sources, run Sublime's
# syntax_tests binary, and parse the result into an LLM-friendly report.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<'EOF'
Usage: run_tests.sh [options]

  --tests-dir DIR           YAML test sources (default: ./yaml_tests, env TESTS_DIR)
  --package-tests-dir DIR   Generated .sublime-syntax-test output
                            (default: ./tests, env PACKAGE_TESTS_DIR)
  --syntax-tests-dir DIR    Where the syntax_tests binary was installed
                            (default: ./st_syntax_tests, env SYNTAX_TESTS_DIR)
  --comment-char CHAR       Fallback comment character for generated tests not
                            covered by the generator's manifest
                            (default: #, env COMMENT_CHAR)
  -h, --help                Show this help

Exit code matches the underlying syntax_tests binary's exit code, except that a
YAML test file failing to convert exits 1 without running the suite.
EOF
}

TESTS_DIR="${TESTS_DIR:-./yaml_tests}"
PACKAGE_TESTS_DIR="${PACKAGE_TESTS_DIR:-./tests}"
SYNTAX_TESTS_DIR="${SYNTAX_TESTS_DIR:-./st_syntax_tests}"
COMMENT_CHAR="${COMMENT_CHAR:-#}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tests-dir) TESTS_DIR="$2"; shift 2 ;;
    --package-tests-dir) PACKAGE_TESTS_DIR="$2"; shift 2 ;;
    --syntax-tests-dir) SYNTAX_TESTS_DIR="$2"; shift 2 ;;
    --comment-char) COMMENT_CHAR="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "error: unknown option '$1'" >&2; usage; exit 1 ;;
  esac
done

if [[ ! -d "$TESTS_DIR" ]] || ! find "$TESTS_DIR" -maxdepth 1 \( -name '*.yaml' -o -name '*.yml' \) -print -quit | grep -q .; then
  echo "error: no .yaml/.yml test files found in '$TESTS_DIR'" >&2
  exit 1
fi

BINARY="$SYNTAX_TESTS_DIR/syntax_tests"
if [[ ! -x "$BINARY" ]]; then
  echo "error: syntax_tests binary not found at '$BINARY'." >&2
  echo "       run scripts/setup_syntax_tests.sh first." >&2
  exit 1
fi

if [[ ! -d "$SYNTAX_TESTS_DIR/Data/Packages" ]] || ! find "$SYNTAX_TESTS_DIR/Data/Packages" -mindepth 1 -maxdepth 1 -print -quit | grep -q .; then
  echo "warning: no package linked under $SYNTAX_TESTS_DIR/Data/Packages -" \
       "re-run setup_syntax_tests.sh with a package path if this wasn't intentional." >&2
fi

if ! "$SCRIPT_DIR/yaml2syntaxtest.py" "$TESTS_DIR" "$PACKAGE_TESTS_DIR"; then
  echo "error: test generation failed - not running the suite, since skipping a" >&2
  echo "       test file would make the run look green." >&2
  exit 1
fi

COMMENT_MAP="$PACKAGE_TESTS_DIR/.comment_chars.json"
PARSE_ARGS=(-c "$COMMENT_CHAR")
[[ -f "$COMMENT_MAP" ]] && PARSE_ARGS+=(--comment-map "$COMMENT_MAP")

RAW_LOG="$(mktemp)"
trap 'rm -f "$RAW_LOG"' EXIT
set +e
"$BINARY" > "$RAW_LOG" 2>&1
ST_EXIT=$?
set -e

"$SCRIPT_DIR/parse_syntax_test.py" "${PARSE_ARGS[@]}" < "$RAW_LOG"

echo
echo "(underlying syntax_tests exit code: $ST_EXIT)"
exit "$ST_EXIT"
