#!/usr/bin/env bash
# Prints one version's section of CHANGELOG.md (the lines after its "## [x.y.z]" heading, up to the
# next "## [" heading), for the GitHub release notes. Fails if the version has no section or the
# section is empty, so a release is never made with blank notes.
#
#   scripts/changelog-section.sh 1.2.3
set -euo pipefail

version="${1:?usage: changelog-section.sh <version without the v>}"
file="$(dirname "$0")/../CHANGELOG.md"

out="$(awk -v v="$version" '
  /^## \[/ { if (on) exit; on = (index($0, "## [" v "]") == 1); next }
  on { print }
' "$file")"

if [[ -z "${out//[[:space:]]/}" ]]; then
  echo "CHANGELOG.md has no section for $version" >&2
  exit 1
fi
printf '%s\n' "$out"
