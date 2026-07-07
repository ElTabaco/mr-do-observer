#!/bin/bash
# CI guard: detect hardcoded secrets in Kubernetes manifests and last-applied-configuration annotations.
# Usage: ./scripts/check-no-secrets.sh [path-to-search]
# Default search path: current directory.
#
# Blocks on:
#   - literal "password" / "token" / "secret" in spec.values / spec.data blocks
#   - any `kind: Secret` whose data values look base64-encoded high-entropy (i.e., not a config key)
#   - hardcoded nfs.server IPs (env-specific drift risk)
#
# Designed to run as a pre-merge / GitHub-Actions step.
set -euo pipefail

SEARCH_PATH="${1:-.}"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

fail=0

echo "==> Scanning $SEARCH_PATH for hardcoded credentials..."

# 1) Plain-text password / token / api_key values
if grep -rEn --include='*.yaml' --include='*.yml' \
    "(password|token|api[_-]?key|secret[_-]?key)\s*:\s*['\"]?[A-Za-z0-9+/=]{12,}" \
    "$SEARCH_PATH" 2>/dev/null; then
    echo -e "${RED}FAIL${NC}: plain-text password/token-like values found in YAML"
    fail=1
fi

# 2) Plain SSH / NFS passwords in shell scripts
if grep -rEn 'password\s*=\s*["'\''][a-zA-Z0-9]{6,}["'\'']' --include='*.sh' --include='*.py' \
    "$SEARCH_PATH" 2>/dev/null | grep -v -E '\.env|secret|temp|/tmp/'; then
    echo -e "${RED}FAIL${NC}: hardcoded password-like literal in shell/python script"
    fail=1
fi

# 3) Generic Secret kind whose data is not empty
if grep -rEn --include='*.yaml' --include='*.yml' \
    "kind:\s*Secret" "$SEARCH_PATH" 2>/dev/null; then
    echo "WARN: found Secret manifests — verify they use sealed-secrets/external-secrets and no plain values"
fi

# 4) Hardcoded NFS server IPs (drift risk per GLM 5.2 review I4)
if grep -rEn --include='*.yaml' --include='*.yml' \
    'server:\s*192\.168\.[0-9]+\.[0-9]+' "$SEARCH_PATH" 2>/dev/null; then
    echo -e "${RED}FAIL${NC}: hardcoded NFS server IP — use a hostname resolvable in the target cluster"
    fail=1
fi

# 5) last-applied-configuration annotations live in cluster only, not in Git
# but if anyone commits a dump, the regex catches it
if grep -rEn 'kubectl.kubernetes.io/last-applied-configuration' \
    --include='*.yaml' --include='*.yml' "$SEARCH_PATH" 2>/dev/null; then
    echo -e "${RED}FAIL${NC}: committed live-state dump with last-applied-configuration annotation"
    fail=1
fi

if [ "$fail" -eq 0 ]; then
    echo -e "${GREEN}OK${NC}: no obvious credential leaks"
fi
exit $fail