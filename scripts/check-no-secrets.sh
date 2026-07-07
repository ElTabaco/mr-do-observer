#!/bin/bash
# CI guard: detect hardcoded secrets in Kubernetes manifests and scripts.
# Usage: ./scripts/check-no-secrets.sh [path-to-search]
set -euo pipefail

SEARCH_PATH="${1:-.}"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

fail=0

echo "==> Scanning $SEARCH_PATH for hardcoded credentials..."

# 1) Plain-text password / token / api_key values in YAML
if grep -rEn --include='*.yaml' --include='*.yml' \
    "(password|token|api[_-]?key|secret[_-]?key)\s*:\s*['\"]?[A-Za-z0-9+/=]{12,}" \
    "$SEARCH_PATH" 2>/dev/null; then
    echo -e "${RED}FAIL${NC}: plain-text password/token-like values found in YAML"
    fail=1
fi

# 2) Plain-text passwords/auth/tokens in shell/python/conf/ini scripts
# Case-insensitive to catch SSH_PASS, AUTH, TOKEN, etc.
# Allows word chars between keyword and [:=] (e.g. SSH_PASS = "...", API_KEY="...")
if grep -rEin --include='*.sh' --include='*.py' --include='*.conf' --include='*.ini' --include='*.cfg' \
    '(pass|auth|token|secret|credential|api[_-]?key)[a-z_]*\s*[:=]\s*["'"'"'][a-zA-Z0-9:/_+=-]{6,}["'"'"']' \
    "$SEARCH_PATH" 2>/dev/null | grep -v -E '\.env|getenv|environ|os\.environ|secretKeyRef|valueFrom|secretRef|<|YOUR_|CHANGE_ME|EXAMPLE|xxxx|placeholder|^\S*:#|^\S*:#'; then
    echo -e "${RED}FAIL${NC}: hardcoded credential literal in script/config"
    fail=1
fi

# 3) Generic Secret kind whose data is not empty
if grep -rEn --include='*.yaml' --include='*.yml' \
    "kind:\s*Secret" "$SEARCH_PATH" 2>/dev/null; then
    echo "WARN: found Secret manifests — verify they use sealed-secrets/external-secrets and no plain values"
fi

# 4) Hardcoded NFS server IPs (drift risk)
if grep -rEn --include='*.yaml' --include='*.yml' \
    'server:\s*192\.168\.[0-9]+\.[0-9]+' "$SEARCH_PATH" 2>/dev/null; then
    echo -e "${RED}FAIL${NC}: hardcoded NFS server IP — use a hostname resolvable in the target cluster"
    fail=1
fi

# 5) last-applied-configuration annotations (live-state dumps)
if grep -rEn 'kubectl.kubernetes.io/last-applied-configuration' \
    --include='*.yaml' --include='*.yml' "$SEARCH_PATH" 2>/dev/null; then
    echo -e "${RED}FAIL${NC}: committed live-state dump with last-applied-configuration annotation"
    fail=1
fi

if [ "$fail" -eq 0 ]; then
    echo -e "${GREEN}OK${NC}: no obvious credential leaks"
fi
exit $fail