#!/usr/bin/env bash
#
# Cut a release: bump versions, build, publish to PyPI, then tag & push.
#
# Usage:
#   ./release.sh [--dry-run] <version>      e.g. ./release.sh 0.1.0
#
# Ordering is deliberate: PyPI upload (immutable, the binding step) happens
# BEFORE the git tag is pushed, so a tag never points at a version that failed
# to publish. Version is written to pyproject.toml AND the HA manifest (its
# own version + the pinned caldera-sauna requirement) so they never drift.
#
# Reads the PyPI token from ~/.pypirc (never printed). Self-provisions a local
# .venv with build+twine — no need to activate anything first.
set -euo pipefail

DRY_RUN=0
POSITIONAL=()
for a in "$@"; do
  case "$a" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \?//'; exit 0 ;;
    -*) echo "unknown option: $a" >&2; exit 2 ;;
    *) POSITIONAL+=("$a") ;;
  esac
done

if [ "${#POSITIONAL[@]}" -ne 1 ]; then
  echo "usage: $0 [--dry-run] <version>" >&2
  exit 2
fi

VERSION="${POSITIONAL[0]#[vV]}"     # accept '0.0.1' or 'v0.0.1'; store without 'v'
TAG="v${VERSION}"                   # git tag is always prefixed 'v'
MANIFEST="custom_components/caldera_sauna/manifest.json"

if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([._-]?(a|b|rc|alpha|beta|dev|post)[0-9]*)?$ ]]; then
  echo "error: '$VERSION' does not look like a version (e.g. 0.1.0)" >&2
  exit 2
fi

cd "$(dirname "$0")"

# --- python env (self-provisioning; no need to pre-activate a venv) ---------
VENV=".venv"
if [ ! -x "$VENV/bin/python" ]; then
  command -v python3 >/dev/null || { echo "error: python3 not found"; exit 1; }
  echo ">> Creating $VENV"
  python3 -m venv "$VENV"
fi
PY="$VENV/bin/python"
if ! "$PY" -c "import build, twine" 2>/dev/null; then
  echo ">> Installing build tooling (build, twine) into $VENV"
  "$PY" -m pip install --quiet --upgrade pip build twine
fi

# --- preconditions ----------------------------------------------------------
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "error: working tree is dirty — commit or stash first"; exit 1
fi
if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
  echo "error: tag $TAG already exists"; exit 1
fi

COMMITTED=0
cleanup() {
  # If we bumped files but never committed (failure or dry-run), restore them.
  if [ "$COMMITTED" -eq 0 ]; then
    git checkout -- pyproject.toml "$MANIFEST" 2>/dev/null || true
  fi
}
trap cleanup EXIT

echo ">> Releasing $TAG (dry-run=$DRY_RUN)"

# --- 1. bump versions in lockstep ------------------------------------------
"$PY" - "$VERSION" "$MANIFEST" <<'PY'
import json, re, sys, pathlib
version, manifest_path = sys.argv[1], sys.argv[2]

pp = pathlib.Path("pyproject.toml")
text, n = re.subn(r'(?m)^version = ".*"$', f'version = "{version}"', pp.read_text(), count=1)
if n != 1:
    sys.exit("could not find 'version = ...' in pyproject.toml")
pp.write_text(text)

mp = pathlib.Path(manifest_path)
data = json.loads(mp.read_text())
data["version"] = version
data["requirements"] = [f"caldera-sauna=={version}"]
mp.write_text(json.dumps(data, indent=2) + "\n")
print(f"   bumped pyproject + manifest to {version}")
PY

# --- 2. clean build + metadata check ---------------------------------------
echo ">> Building"
rm -rf dist build ./*.egg-info src/*.egg-info
"$PY" -m build >/dev/null
"$PY" -m twine check dist/*

if [ "$DRY_RUN" -eq 1 ]; then
  echo ">> [dry-run] built and checked OK. Would now:"
  echo "     git commit -am 'Release $TAG'"
  echo "     twine upload --skip-existing dist/*"
  echo "     git tag $TAG && git push origin HEAD && git push origin $TAG"
  echo ">> [dry-run] reverting version bump, no side effects."
  exit 0
fi

# --- 3. publish to PyPI FIRST (the immutable step) -------------------------
echo ">> Uploading to PyPI"
"$PY" -m twine upload --skip-existing dist/*

# --- 4. commit, tag, push (only after a successful upload) -----------------
echo ">> Committing, tagging, pushing"
git commit -am "Release $TAG"
COMMITTED=1
git tag -a "$TAG" -m "Release $TAG"
git push origin HEAD
git push origin "$TAG"

echo ">> Released $TAG ✓  (PyPI: caldera-sauna $VERSION; git tag $TAG pushed)"
