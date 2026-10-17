#!/usr/bin/env bash
# Download the APK that GitHub Actions released for v<version> into downloads/,
# after checking its checksum and release signature. Publishing (downloads-seed,
# then flipping downloads/app-release.json) stays a separate, deliberate step.
#
#   scripts/android-github-fetch.sh 1.0.24
#
# Needs a fine-grained GitHub token with read access to the private repo's
# contents, stored by the operator in $TOKEN_FILE (never in the repo).
set -euo pipefail

VERSION="${1:?usage: $0 <versionName>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="${ANDROID_REPO:-poywcvg/revayato-android}"
TOKEN_FILE="${GITHUB_TOKEN_FILE:-/root/.config/revayato/github-token}"
EXPECTED_CERT=741b8ce2e3638ed4f1120675ad5bf95bbec16b787cb7ce20ce709bcb42b6e947
OUT="$ROOT/downloads/revayato-$VERSION.apk"

TOKEN="$(cat "$TOKEN_FILE")"
api() { curl -fsSL -H "Authorization: Bearer $TOKEN" -H "X-GitHub-Api-Version: 2022-11-28" "$@"; }

RELEASE=$(api "https://api.github.com/repos/$REPO/releases/tags/v$VERSION")
asset_id() { echo "$RELEASE" | python3 -c "import sys,json; print(next(a['id'] for a in json.load(sys.stdin)['assets'] if a['name']==sys.argv[1]))" "$1"; }

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
api -H "Accept: application/octet-stream" -o "$TMP/app.apk" "https://api.github.com/repos/$REPO/releases/assets/$(asset_id "revayato-$VERSION.apk")"
api -H "Accept: application/octet-stream" -o "$TMP/app.sha256" "https://api.github.com/repos/$REPO/releases/assets/$(asset_id "revayato-$VERSION.apk.sha256")"

[ "$(sha256sum "$TMP/app.apk" | cut -d' ' -f1)" = "$(cut -d' ' -f1 "$TMP/app.sha256")" ] || { echo "checksum mismatch" >&2; exit 1; }

BT=$(ls -d "${ANDROID_HOME:-/opt/android-sdk}"/build-tools/* | sort -V | tail -1)
CERT=$("$BT/apksigner" verify --print-certs "$TMP/app.apk" | sed -n 's/.*certificate SHA-256 digest: //p' | head -1)
[ "$CERT" = "$EXPECTED_CERT" ] || { echo "wrong signing certificate: $CERT" >&2; exit 1; }
"$BT/aapt2" dump badging "$TMP/app.apk" | head -1

cp "$TMP/app.apk" "$OUT"
ls -l "$OUT"
echo "next: seed the downloads volume, check the URL, then flip downloads/app-release.json"
