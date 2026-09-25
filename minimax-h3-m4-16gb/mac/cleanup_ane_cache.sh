#!/bin/zsh
set -euo pipefail

echo "h3.c-ane compiles fixed-shape ANE programs."
echo "The project cache may be ~19 GB per unique shape, and Apple's aned cache can keep another copy."
echo

CACHE="${TMPDIR:-/tmp}/h3-ane-cache"
if [[ -d "$CACHE" ]]; then
  du -sh "$CACHE" || true
else
  echo "No h3 ANE cache at $CACHE"
fi

if [[ -d /Library/Caches/com.apple.aned ]]; then
  sudo du -sh /Library/Caches/com.apple.aned || true
fi

echo
read "REPLY?Delete both ANE caches now? [y/N] "
if [[ "$REPLY" == [yY] ]]; then
  rm -rf "$CACHE"
  sudo rm -rf /Library/Caches/com.apple.aned/*
  echo "Caches deleted. They will be rebuilt on the next run."
else
  echo "No changes made."
fi
