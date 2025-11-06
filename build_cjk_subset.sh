#!/usr/bin/env bash
set -euo pipefail

ZIP="$HOME/Downloads/Noto_Sans_SC.zip"
OUT_DIR="$HOME/Downloads"
SIZE=16

# === Characters to include ===
CHARSET=$'现在在是温度度华氏摄氏天气晴多云小雨中雨大雨阵雨雾风速湿度气压旧金山加州美国湾区戴利城'
CHARSET+=$'0123456789:% .°F℃()/–-,:;!?'
CHARSET+=$'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'

# === Find tools ===
if command -v pyftsubset >/dev/null 2>&1; then
  SUBSET_CMD="pyftsubset"
else
  SUBSET_CMD="pipx run fonttools pyftsubset"
fi

if command -v otf2bdf >/dev/null 2>&1; then
  CONVERTER="otf2bdf"
elif command -v ttf2bdf >/dev/null 2>&1; then
  CONVERTER="ttf2bdf"
else
  echo "❌ No BDF converter. Install: brew install otf2bdf"
  exit 1
fi

# === Workspace ===
WORKDIR="$HOME/Downloads/cjkfont_temp"
rm -rf "$WORKDIR"
mkdir -p "$WORKDIR"
 
echo "📦 Unzipping $ZIP ..."
unzip -q "$ZIP" -d "$WORKDIR"

FONT_FILE=$(find "$WORKDIR" -type f \( -iname '*Regular*.ttf' -o -iname '*Regular*.otf' \) | head -n 1)
if [[ -z "${FONT_FILE:-}" ]]; then
  FONT_FILE=$(find "$WORKDIR" -type f \( -iname '*.ttf' -o -iname '*.otf' \) | head -n 1)
fi
[[ -n "$FONT_FILE" ]] || { echo "❌ No .ttf/.otf found after unzip."; exit 1; }
echo "Using font: $FONT_FILE"

echo "✂️  Creating subset TTF ..."
$SUBSET_CMD "$FONT_FILE" \
  --text="$CHARSET" \
  --output-file="$WORKDIR/subset.ttf" \
  --glyph-names \
  --no-hinting \
  --ignore-missing-glyphs \
  --layout-features='*' \
  --drop-tables+=GSUB,GPOS

# === Convert to bitmap BDF ===
BDF="$OUT_DIR/cjk${SIZE}.bdf"
echo "🖼  Converting to bitmap BDF (${SIZE}px) ..."
$CONVERTER -p "$SIZE" "$WORKDIR/subset.ttf" > "$BDF"

echo
echo "✅ Font generated: $BDF"
echo "➡️  Copy to CIRCUITPY/fonts/ and use /fonts/cjk${SIZE}.bdf in your code."
