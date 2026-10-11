#!/bin/sh
set -eu
: "${RELEASE_ID:?set fixed release ID}" "${TARGET_PLATFORM:?linux/amd64 or linux/arm64}"
case "$RELEASE_ID" in *[!a-zA-Z0-9._-]*|'') exit 2;; esac
case "$TARGET_PLATFORM" in linux/amd64|linux/arm64) ;; *) exit 2;; esac
archive="images-$RELEASE_ID.tar"
manifest="images-$RELEASE_ID.manifest.jsonl"
test ! -e "$archive"
test ! -e "$manifest"
docker pull --platform "$TARGET_PLATFORM" postgres:18.6-bookworm
# Run on a Linux builder with adequate memory. Build serially, never on boot.
docker build --platform "$TARGET_PLATFORM" -f deploy/Dockerfile.api -t "game-of-life-api:$RELEASE_ID" .
docker build --platform "$TARGET_PLATFORM" -f deploy/Dockerfile.web -t "game-of-life-web:$RELEASE_ID" .
docker build --platform "$TARGET_PLATFORM" -f deploy/Dockerfile.ops -t "game-of-life-ops:$RELEASE_ID" .
docker image inspect --format '{"id":{{json .Id}},"platform":"{{.Os}}/{{.Architecture}}","tags":{{json .RepoTags}}}' "game-of-life-api:$RELEASE_ID" "game-of-life-web:$RELEASE_ID" "game-of-life-ops:$RELEASE_ID" postgres:18.6-bookworm > "$manifest"
# No registry publishing is performed. Save to a new file, never overwrite the last release.
docker save -o "$archive" "game-of-life-api:$RELEASE_ID" "game-of-life-web:$RELEASE_ID" "game-of-life-ops:$RELEASE_ID" postgres:18.6-bookworm
sha256sum "$archive" "$manifest" > "$archive.sha256"
