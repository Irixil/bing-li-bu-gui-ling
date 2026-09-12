#!/bin/zsh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
swiftc -O -framework Vision -framework ImageIO "$ROOT/tools/media-recognition/vision_ocr.swift" -o "$ROOT/tools/media-recognition/vision_ocr"
echo "built $ROOT/tools/media-recognition/vision_ocr"
