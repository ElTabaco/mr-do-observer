#!/usr/bin/env bash
# Install the monitoring exporters on an LLM server (Ubuntu + NVIDIA + llama-server).
# Idempotent: safe to re-run. Does NOT touch llama-server.service.
#
#   sudo bash install-exporters.sh            # run from this directory
#
# Installs:
#   prometheus-node-exporter (apt)      :9100  host CPU/RAM/disk/net + textfile collector
#   nvidia-gpu-exporter      (GitHub)   :9835  GPU util/VRAM/temp/power/clocks via nvidia-smi
#   llm-model-info.timer     (local)           writes llm_model.prom every 30 s from llama-server /props
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

echo "== nvidia-gpu-exporter ${NGX_VERSION}"
if [ "$(dpkg-query -W -f='${Version}' nvidia-gpu-exporter 2>/dev/null || true)" != "$NGX_VERSION" ]; then
  deb="$(mktemp --suffix=.deb)"
  curl -fsSL -o "$deb" "$NGX_URL"
  echo "${NGX_SHA256}  ${deb}" | sha256sum -c -
  dpkg -i "$deb"
  rm -f "$deb"
fi

echo "== llm-model-info"
install -m 0755 "$HERE/llm-model-info.py" /usr/local/bin/llm-model-info
install -m 0644 "$HERE/llm-model-info.service" "$HERE/llm-model-info.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now prometheus-node-exporter.service nvidia_gpu_exporter.service llm-model-info.timer
systemctl start llm-model-info.service

echo "== status"
systemctl is-active prometheus-node-exporter nvidia_gpu_exporter llm-model-info.timer llama-server
cat /etc/default/prometheus-node-exporter 2>/dev/null | grep -v '^#' | grep -v '^$' || true
ls -l "$TEXTFILE_DIR"
