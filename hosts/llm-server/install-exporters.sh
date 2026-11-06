#!/usr/bin/env bash
# Install the monitoring exporters on an LLM server (Ubuntu + NVIDIA or AMD + llama-server or Strata).
# Idempotent: safe to re-run. Does NOT touch the engine units (llama-server / strata-server).
#
#   sudo bash install-exporters.sh            # run from this directory
#
# Installs:
#   prometheus-node-exporter (apt)      :9100  host CPU/RAM/disk/net + textfile collector
#   nvidia-gpu-exporter      (GitHub)   :9835  NVIDIA only: GPU util/VRAM/temp/power/clocks via nvidia-smi
#   llm-model-info.timer     (local)           writes llm_model.prom every 10 s (/props, /slots, AMD GPU sysfs)
set -euo pipefail

NGX_VERSION="${NGX_VERSION:-1.17.0}"
NGX_SHA256="${NGX_SHA256:-1bc0f7f811579a7505ed284e9cdcea1a454f3101da2c60877a7aaafb15fecde4}"
NGX_URL="https://github.com/utkuozdemir/nvidia_gpu_exporter/releases/download/v${NGX_VERSION}/nvidia-gpu-exporter_${NGX_VERSION}_linux_amd64.deb"
TEXTFILE_DIR="/var/lib/prometheus/node-exporter"
HERE="$(cd "$(dirname "$0")" && pwd)"

[ "$(id -u)" = 0 ] || { echo "run as root (sudo)"; exit 1; }

echo "== node-exporter"
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends prometheus-node-exporter
install -d -o prometheus -g prometheus -m 0755 "$TEXTFILE_DIR"

if command -v nvidia-smi >/dev/null 2>&1; then
  echo "== nvidia-gpu-exporter ${NGX_VERSION} (NVIDIA GPU found)"
  if [ "$(dpkg-query -W -f='${Version}' nvidia-gpu-exporter 2>/dev/null || true)" != "$NGX_VERSION" ]; then
    deb="$(mktemp --suffix=.deb)"
    curl -fsSL -o "$deb" "$NGX_URL"
    echo "${NGX_SHA256}  ${deb}" | sha256sum -c -
    dpkg -i "$deb"
    rm -f "$deb"
  fi
  GPU_UNITS=nvidia_gpu_exporter.service
else
  echo "== no nvidia-smi: skipping nvidia-gpu-exporter (AMD GPUs are exported by llm-model-info as llm_gpu_*)"
  GPU_UNITS=""
fi

echo "== llm-model-info"
install -m 0755 "$HERE/llm-model-info.py" /usr/local/bin/llm-model-info
install -m 0644 "$HERE/llm-model-info.service" "$HERE/llm-model-info.timer" /etc/systemd/system/
# Read-only view of the model directory (only that, home stays hidden): the GGUF header fallback for engines
# without /v1/models meta (Strata). LLM_MODELS_DIR overrides; default = the ".../models" or ".../huggingface/hub"
# root of the running engine's /props model_path.
MODELS_DIR="${LLM_MODELS_DIR:-$(curl -fsS --max-time 10 http://127.0.0.1:8080/props 2>/dev/null | python3 -c '
import json, os, re, sys
p = json.load(sys.stdin).get("model_path", "")
m = re.match(r"(.*/(?:models|huggingface/hub))/", p)
print(m.group(1) if m else os.path.dirname(p))' 2>/dev/null || true)}"
DROPIN=/etc/systemd/system/llm-model-info.service.d/10-models-dir.conf
if [ -n "$MODELS_DIR" ] && [ -d "$MODELS_DIR" ]; then
  install -d -m 0755 "$(dirname "$DROPIN")"
  printf '[Service]\nProtectHome=tmpfs\nBindReadOnlyPaths=-%s\n' "$MODELS_DIR" > "$DROPIN"
  echo "   models dir (read-only for llm-model-info): $MODELS_DIR"
else
  echo "   no models dir found (engine down?) - parameters/size only from /v1/models meta"
fi
systemctl daemon-reload
systemctl enable --now prometheus-node-exporter.service $GPU_UNITS llm-model-info.timer
systemctl start llm-model-info.service

echo "== status"
systemctl is-active prometheus-node-exporter $GPU_UNITS llm-model-info.timer llama-server strata-server || true
cat /etc/default/prometheus-node-exporter 2>/dev/null | grep -v '^#' | grep -v '^$' || true
ls -l "$TEXTFILE_DIR"
