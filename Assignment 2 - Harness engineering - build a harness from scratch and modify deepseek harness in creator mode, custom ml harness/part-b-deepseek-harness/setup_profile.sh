#!/usr/bin/env bash
# Customise a DeepSeek Harness profile with 6 existing plugins + our own.
#   ./setup_profile.sh            # profile "web" (has Creator mode)
# Needs Node 22+, pnpm, git. DSH itself: npm i -g @deepseek-ai/dsh  (tested with 0.2.1-rc.5)
set -euo pipefail
cd "$(dirname "$0")"; HERE="$PWD"; PROFILE="${PROFILE:-web}"
DSH="${DSH:-dsh}"; VER="$($DSH --version)"
COMMUNITY="$HERE/community"; mkdir -p "$COMMUNITY"

echo "== 1-4: DeepSeek's in-box optional bundles (pinned to the running DSH version $VER)"
for b in ralph session-titles terminal plugin-market; do
  $DSH plugin --profile "$PROFILE" add "@deepseek-ai/dsh-experimental-$b-bundle@$VER"
done

echo "== 5-6: community plugins (pinned commits; their deps installed with scripts disabled)"
clone() { [ -d "$COMMUNITY/$2" ] || git clone -q https://github.com/$1 "$COMMUNITY/$2"; git -C "$COMMUNITY/$2" checkout -q "$3"; }
clone aa2246740/dsh-creator-mode-plus creator-mode-plus cc641bca35f1
clone Ephemeral-AI-Lab/dsh-plugins ephemeral cb9ea007a6b4
(cd "$COMMUNITY/creator-mode-plus" && npm i --omit=dev --omit=peer --ignore-scripts --no-audit --no-fund)
$DSH plugin --profile "$PROFILE" add "$COMMUNITY/creator-mode-plus"
$DSH plugin --profile "$PROFILE" add "$COMMUNITY/ephemeral/plugins/sessions"
# Tried and removed: Ephemeral's dsh-loop imports `CallId` from dsh-llm 0.1 and fails on DSH 0.2.

echo "== 7-9: our plugins (written from scratch)"
$DSH plugin --profile "$PROFILE" add "$HERE/plugins/dsh-second-brain"
$DSH plugin --profile "$PROFILE" add "$HERE/plugins/dsh-dataset-profiler"
$DSH plugin --profile "$PROFILE" add "$HERE/../part-c-ml-autoresearch-harness/dsh-autoresearch"

echo; echo "Profile '$PROFILE' bundles:"; $DSH --profile "$PROFILE" --dump-config | grep '^# == ' 
echo; echo "Start it:  $DSH web     (then pick 'Creator mode' in the mode menu)"
