#!/usr/bin/env bash
# Download and extract Sublime Text's official syntax_tests binary, and
# optionally symlink a package directory into its Data/Packages/ so
# `Packages/<name>/...` resolves in YAML test `syntax:` fields.
#
# Usage: setup_syntax_tests.sh [build] [target_dir] [package_path] [package_name]
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: setup_syntax_tests.sh [build] [target_dir] [package_path] [package_name]

  build         Sublime Text build number (default: 4200, env SUBLIME_BUILD)
  target_dir    Where to download/extract the binary (default: ./st_syntax_tests,
                env SYNTAX_TESTS_DIR)
  package_path  Path to a package directory to link in for testing (optional)
  package_name  Name to link it under, i.e. Packages/<package_name>/...
                (default: basename of package_path)

Env vars:
  SUBLIME_BUILD, SYNTAX_TESTS_DIR   see above
  FORCE=1                           force re-download and re-link even if
                                     already present
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

BUILD="${1:-${SUBLIME_BUILD:-4200}}"
TARGET_DIR="${2:-${SYNTAX_TESTS_DIR:-./st_syntax_tests}}"
PACKAGE_PATH="${3:-}"
PACKAGE_NAME="${4:-}"
FORCE="${FORCE:-}"

if [[ ! "$BUILD" =~ ^[0-9]+$ ]]; then
  echo "error: build number must be numeric, got '$BUILD'" >&2
  exit 1
fi

OS="$(uname -s)"
ARCH="$(uname -m)"
if [[ "$OS" != "Linux" || "$ARCH" != "x86_64" ]]; then
  echo "error: this tool only supports Linux x64 (detected $OS/$ARCH)." >&2
  echo "Sublime does not publish the syntax_tests binary for other platforms." >&2
  exit 1
fi

if (( BUILD < 4000 )); then
  URL="https://download.sublimetext.com/st3_syntax_tests_build_${BUILD}_x64.tar.bz2"
elif (( BUILD < 4079 )); then
  URL="https://download.sublimetext.com/st_syntax_tests_build_${BUILD}_x64.tar.bz2"
else
  URL="https://download.sublimetext.com/st_syntax_tests_build_${BUILD}_x64.tar.xz"
fi

BINARY="$TARGET_DIR/syntax_tests"

if [[ -x "$BINARY" && -z "$FORCE" ]]; then
  INSTALLED_BUILD="$(cat "$TARGET_DIR/.build_version" 2>/dev/null || echo unknown)"
  echo "already set up at $TARGET_DIR (installed build: $INSTALLED_BUILD)"
  if [[ "$INSTALLED_BUILD" != "$BUILD" ]]; then
    echo "warning: requested build $BUILD differs from installed build $INSTALLED_BUILD." >&2
    echo "         set FORCE=1 to re-download build $BUILD." >&2
  fi
else
  mkdir -p "$TARGET_DIR"
  TMPFILE="$(mktemp)"
  trap 'rm -f "$TMPFILE"' EXIT

  echo "Fetching build $BUILD from $URL ..."
  if command -v curl >/dev/null 2>&1; then
    if ! curl -fL -o "$TMPFILE" "$URL"; then
      echo "error: failed to download $URL (check the build number exists at download.sublimetext.com)" >&2
      exit 1
    fi
  elif command -v wget >/dev/null 2>&1; then
    if ! wget -O "$TMPFILE" "$URL"; then
      echo "error: failed to download $URL (check the build number exists at download.sublimetext.com)" >&2
      exit 1
    fi
  else
    echo "error: need curl or wget installed to download the syntax_tests binary" >&2
    exit 1
  fi

  # The archive contains a single top-level directory (e.g. st_syntax_tests/)
  # wrapping syntax_tests + Data/ + LICENSE; strip it so $TARGET_DIR itself
  # is that directory's contents.
  tar -xf "$TMPFILE" -C "$TARGET_DIR" --strip-components=1

  if [[ ! -e "$BINARY" ]]; then
    echo "error: archive layout unexpected, syntax_tests not found under $TARGET_DIR" >&2
    exit 1
  fi
  chmod +x "$BINARY"
  echo "$BUILD" > "$TARGET_DIR/.build_version"
  echo "Installed syntax_tests (build $BUILD) at $BINARY"
fi

if [[ -n "$PACKAGE_PATH" ]]; then
  if [[ ! -d "$PACKAGE_PATH" ]]; then
    echo "error: package_path '$PACKAGE_PATH' is not a directory" >&2
    exit 1
  fi
  ABS_PATH="$(cd "$PACKAGE_PATH" && pwd)"
  NAME="${PACKAGE_NAME:-$(basename "$ABS_PATH")}"
  PACKAGES_DIR="$TARGET_DIR/Data/Packages"
  mkdir -p "$PACKAGES_DIR"
  LINK="$PACKAGES_DIR/$NAME"

  ABS_TARGET="$(cd "$TARGET_DIR" && pwd)"

  # Link each top-level entry into a real directory rather than symlinking
  # package_path wholesale. When package_path is the repo root (the usual layout
  # for a Sublime package), a whole-directory symlink puts target_dir back
  # underneath Data/Packages/<name>: the binary then reaches its own
  # Data/Packages through the link, warns "has been seen before, skipping (using
  # inode)" and exits 1 even when every assertion passed.
  #
  # -L as well as -e: a dangling symlink (package_path since moved or renamed)
  # fails -e, and the bare `ln -s` below would then die with "File exists".
  if [[ -L "$LINK" ]]; then
    rm "$LINK"
  fi
  mkdir -p "$LINK"
  # Drop stale entry links so a file removed from the package stops being tested.
  find "$LINK" -maxdepth 1 -type l -delete

  LINKED=0
  # Unquoted glob skips dotfiles, so .git/.github/.gitignore stay out.
  for entry in "$ABS_PATH"/*; do
    [[ -e "$entry" ]] || continue
    base="$(basename "$entry")"
    if [[ "$ABS_TARGET" == "$entry" || "$ABS_TARGET" == "$entry"/* ]]; then
      echo "  skipped $base/ (holds the syntax_tests binary)"
      continue
    fi
    ln -sfn "$entry" "$LINK/$base"
    LINKED=$((LINKED + 1))
  done

  if (( LINKED == 0 )); then
    echo "error: nothing to link from '$ABS_PATH'" >&2
    exit 1
  fi
  echo "linked $LINKED entr$( ((LINKED == 1)) && echo y || echo ies ) from $ABS_PATH into $LINK"
  echo "Use \"Packages/$NAME/...\" in your YAML tests' syntax: field."
  echo "Re-run this script after adding a new top-level file to the package."
fi

echo "Done. Binary: $BINARY"
