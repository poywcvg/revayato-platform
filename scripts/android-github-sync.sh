#!/usr/bin/env bash
# Mirror android/ into the private GitHub repo that builds the release APK.
#
#   scripts/android-github-sync.sh            push the current source
#   scripts/android-github-sync.sh --tag      push, then tag v<versionName> → GitHub builds + releases it
#
# The mirror lives in $MIRROR (its own git repo, remote = the private repo,
# pushed through the `github-android` SSH host alias and its deploy key).
# Signing files, local SDK paths and build output never leave this machine.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MIRROR="${ANDROID_MIRROR:-/root/revayato-android}"
REMOTE="${ANDROID_REMOTE:-git@github-android:poywcvg/revayato-android.git}"

if [ ! -d "$MIRROR/.git" ]; then
  git init -q -b main "$MIRROR"
  git -C "$MIRROR" remote add origin "$REMOTE"
fi

rsync -a --delete \
  --exclude '.git/' \
  --exclude 'keystore.properties' --exclude '*.keystore' --exclude '*.jks' \
  --exclude 'local.properties' --exclude 'backup.env' \
  --exclude '.gradle/' --exclude '.kotlin/' --exclude 'build/' --exclude '*/build/' \
  --exclude '*.apk' --exclude '.idea/' --exclude '*.iml' \
  "$ROOT/android/" "$MIRROR/"

cat > "$MIRROR/.gitignore" <<'EOF'
keystore.properties
*.keystore
*.jks
local.properties
backup.env
.gradle/
.kotlin/
build/
*.apk
.idea/
*.iml
EOF

# Last line of defence: refuse to push if anything secret slipped through.
if find "$MIRROR" -path "$MIRROR/.git" -prune -o \( -name 'keystore.properties' -o -name '*.keystore' -o -name '*.jks' -o -name 'local.properties' \) -print | grep -q .; then
  echo "refusing: signing or local files found in $MIRROR" >&2
  exit 1
fi

VERSION=$(sed -n 's/.*versionName = "\([^"]*\)".*/\1/p' "$MIRROR/app/build.gradle.kts" | head -1)

git -C "$MIRROR" add -A
if git -C "$MIRROR" diff --cached --quiet; then
  echo "no source changes"
else
  git -C "$MIRROR" commit -q -m "Android $VERSION"
fi
git -C "$MIRROR" push -q origin main
echo "pushed Android $VERSION"

if [ "${1:-}" = "--tag" ]; then
  git -C "$MIRROR" tag -f "v$VERSION"
  git -C "$MIRROR" push -q -f origin "v$VERSION"
  echo "tagged v$VERSION — GitHub Actions is building the release APK"
fi
