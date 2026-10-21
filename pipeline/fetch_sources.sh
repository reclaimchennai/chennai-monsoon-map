#!/bin/bash
# Fetch the source files that are too big for git, and verify them.
#   raw/cdmp/*.pdf          GCC City Disaster Management Plan PDFs (mirrored as GitHub release assets)
#   raw/swd/network.json    storm-water-drain network (github.com/reclaimchennai/chennai-swd)
set -e
cd "$(dirname "$0")/.."
REL=https://github.com/reclaimchennai/chennai-monsoon-map/releases/download/sources
mkdir -p raw/cdmp raw/swd
for f in $(cut -d' ' -f3 raw/cdmp/SHA256SUMS); do
  [ -f raw/cdmp/$f ] || curl -L --fail -o raw/cdmp/$f $REL/$f
done
(cd raw/cdmp && shasum -a 256 -c SHA256SUMS)
[ -f raw/swd/network.json ] || curl -L --fail -o raw/swd/network.json https://swd.reclaimchennai.city/data/network.json
echo "sources ready"
