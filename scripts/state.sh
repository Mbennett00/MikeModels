#!/usr/bin/env bash
# Sync ./state with the `data-latest` GitHub release (needs GH_TOKEN with contents:write).
#   scripts/state.sh pull   download site files + intermediate.tar.gz into ./state
#   scripts/state.sh push   upload ./state/site/* and a fresh intermediate.tar.gz
set -euo pipefail
TAG=data-latest
mkdir -p state/site state/intermediate
case "$1" in
  pull)
    if ! gh release view "$TAG" >/dev/null 2>&1; then
      gh release create "$TAG" --title "Model data (auto-updated)" --prerelease \
        --notes "Written by the daily workflow. The dashboard reads these files. Do not edit by hand."
    fi
    rm -rf state/dl && mkdir -p state/dl
    gh release download "$TAG" -D state/dl --clobber || true
    if [ -f state/dl/intermediate.tar.gz ]; then tar xzf state/dl/intermediate.tar.gz -C state; fi
    find state/dl -maxdepth 1 -type f ! -name intermediate.tar.gz -exec mv -f {} state/site/ \;
    # the prediction database travels gzipped
    if [ -f state/site/model_db.sqlite.gz ]; then gunzip -f state/site/model_db.sqlite.gz; fi
    ls -la state/site state/intermediate
    ;;
  push)
    tar czf state/intermediate.tar.gz -C state intermediate
    files=(state/intermediate.tar.gz)
    if [ -f state/site/model_db.sqlite ]; then gzip -kf state/site/model_db.sqlite; fi
    for f in state/site/*; do
      [ -f "$f" ] || continue
      [ "$(basename "$f")" = "model_db.sqlite" ] && continue     # uploaded as model_db.sqlite.gz
      files+=("$f")
    done
    gh release upload "$TAG" "${files[@]}" --clobber
    ;;
  *) echo "usage: $0 pull|push"; exit 2 ;;
esac
