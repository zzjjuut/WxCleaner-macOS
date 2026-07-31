#!/usr/bin/env bash
set -euo pipefail

APP_VERSION="${APP_VERSION:-2.0.0}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VENV_DIR="${VENV_DIR:-environment/.venv}"
PYTHON="$VENV_DIR/bin/python"

find_python_with_tk() {
  if [[ -n "${PYTHON_BOOTSTRAP:-}" ]]; then
    printf '%s\n' "$PYTHON_BOOTSTRAP"
    return
  fi

  local candidates=(
    "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
    "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3"
    "/usr/local/bin/python3"
    "/usr/bin/python3"
    "python3"
  )

  local candidate
  for candidate in "${candidates[@]}"; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import tkinter" >/dev/null 2>&1; then
      command -v "$candidate"
      return
    fi
  done

  echo "No Python with tkinter found. Set PYTHON_BOOTSTRAP=/path/to/python3." >&2
  return 1
}

if [[ ! -x "$PYTHON" ]]; then
  BOOTSTRAP_PYTHON="$(find_python_with_tk)"
  "$BOOTSTRAP_PYTHON" -m venv "$VENV_DIR"
fi

"$PYTHON" -c "import tkinter"

"$PYTHON" -m pip install --upgrade pip
"$PYTHON" -m pip install -r requirements.txt pyinstaller pytest
if [[ "${SKIP_TESTS:-0}" != "1" ]]; then
  "$PYTHON" -m pytest tests -v
fi

rm -rf build/pyinstaller
mkdir -p app build/release

"$VENV_DIR/bin/pyinstaller" \
  --noconfirm \
  --clean \
  --distpath build/pyinstaller/dist \
  --workpath build/pyinstaller/work \
  packaging/WxCleaner.spec

APP_SRC="build/pyinstaller/dist/WxCleaner.app"
APP_DST="app/WxCleaner-${APP_VERSION}.app"
ZIP_PATH="build/release/WxCleaner-macOS-arm64-v${APP_VERSION}.zip"

rm -rf "$APP_DST" "$ZIP_PATH" "$ZIP_PATH.sha256"
ditto "$APP_SRC" "$APP_DST"
xattr -cr "$APP_DST"

if ! codesign --verify --deep --strict "$APP_DST"; then
  codesign --force --deep --sign - "$APP_DST"
fi

codesign --verify --deep --strict --verbose=2 "$APP_DST"
file "$APP_DST/Contents/MacOS/WxCleaner" | grep -q "arm64"

COPYFILE_DISABLE=1 ditto -c -k --norsrc --keepParent "$APP_DST" "$ZIP_PATH"
shasum -a 256 "$ZIP_PATH" > "$ZIP_PATH.sha256"

echo "Built $APP_DST"
echo "Packaged $ZIP_PATH"
