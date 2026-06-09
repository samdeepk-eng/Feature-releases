#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"
BUILD_DIR="${BUILD_DIR:-build}"
ZIP_FILE="${ZIP_FILE:-lambda.zip}"
LAMBDA_PYTHON_VERSION="${LAMBDA_PYTHON_VERSION:-3.14}"
LAMBDA_ARCHITECTURE="${LAMBDA_ARCHITECTURE:-x86_64}"

case "$LAMBDA_ARCHITECTURE" in
  x86_64)
    PIP_PLATFORM="manylinux2014_x86_64"
    ;;
  arm64)
    PIP_PLATFORM="manylinux2014_aarch64"
    ;;
  *)
    echo "Unsupported LAMBDA_ARCHITECTURE: $LAMBDA_ARCHITECTURE" >&2
    exit 1
    ;;
esac

PYTHON_ABI="cp${LAMBDA_PYTHON_VERSION/./}"

rm -rf "$BUILD_DIR" "$ZIP_FILE"
mkdir -p "$BUILD_DIR"

"$PYTHON_BIN" -m pip install \
  --upgrade \
  --no-compile \
  --target "$BUILD_DIR" \
  --platform "$PIP_PLATFORM" \
  --implementation cp \
  --python-version "$LAMBDA_PYTHON_VERSION" \
  --abi "$PYTHON_ABI" \
  --only-binary=:all: \
  -r requirements.txt
cp -R app "$BUILD_DIR/app"

(
  cd "$BUILD_DIR"
  zip -r "../$ZIP_FILE" .
)

echo "Created $ZIP_FILE"
