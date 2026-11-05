#!/usr/bin/env bash
# Verifies that every API route on a deployment reaches its function instead of
# falling through to the SPA fallback.
#
#   ./scripts/check-routes.sh https://your-deployment.vercel.app [?_vercel_share=TOKEN]
#
# This exists because Vercel resolves routes as: filesystem -> rewrites ->
# dynamic routes. A SPA rewrite of "/(.*)" therefore swallows catch-all API
# routes such as /api/data/[...path] before they are ever considered, and the
# symptom is a 200 serving index.html rather than an error. The rewrite source
# must exclude /api/.
set -u
BASE="${1:?usage: check-routes.sh BASE_URL [SHARE_QUERY]}"
SHARE="${2:-}"
JAR="$(mktemp)"; trap 'rm -f "$JAR"' EXIT
fails=0

probe() {
  local path="$1" expect="$2"
  local sep='?'; [[ "$path" == *'?'* ]] && sep='&'
  local url="${BASE}${path}"
  [[ -n "$SHARE" ]] && url="${url}${sep}${SHARE#\?}"

  local body
  body=$(curl -s -L --max-time 25 -c "$JAR" -b "$JAR" "$url" 2>/dev/null | head -c 200)

  if grep -qi '<!doctype html>' <<<"$body"; then
    printf '  \033[31mFAIL\033[0m  %-42s served index.html (function not matched)\n' "$path"
    fails=$((fails+1))
  elif [[ -n "$expect" ]] && ! grep -q "$expect" <<<"$body"; then
    printf '  \033[31mFAIL\033[0m  %-42s unexpected: %s\n' "$path" "${body:0:80}"
    fails=$((fails+1))
  else
    printf '  \033[32mPASS\033[0m  %-42s %s\n' "$path" "${body:0:70}"
  fi
}

echo "Checking API routing on ${BASE}"
probe "/api/health"                        ""
probe "/api/data/projects"                 ""
probe "/api/data/projects/not-a-uuid"      "UUID"
probe "/api/data/experts/not-a-uuid"       "UUID"
probe "/api/data/nonexistent"              "Unknown resource"
probe "/api/outreach/export?campaign_id=x" ""
probe "/api/projects/from-document"        "Method not allowed"

echo
if [[ $fails -eq 0 ]]; then echo -e "\033[32mAll routes resolve to functions.\033[0m"; else
  echo -e "\033[31m${fails} route(s) did not reach a function.\033[0m"; fi
exit $(( fails == 0 ? 0 : 1 ))
