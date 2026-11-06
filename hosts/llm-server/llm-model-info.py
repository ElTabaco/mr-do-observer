#!/usr/bin/env python3
"""Export the model served by llama-server as Prometheus metrics (node-exporter textfile collector).

Reads llama-server /props, /v1/models and /slots and atomically writes <TEXTFILE_DIR>/llm_model.prom.
Run by llm-model-info.timer every 10 s. Stdlib only.

Environment:
  LLM_URL       llama-server base URL          (default http://127.0.0.1:8080)
  TEXTFILE_DIR  node-exporter textfile dir     (default /var/lib/prometheus/node-exporter)
"""
import json
import os
import re
import tempfile
import time
import urllib.request

LLM_URL = os.environ.get("LLM_URL", "http://127.0.0.1:8080").rstrip("/")
TEXTFILE_DIR = os.environ.get("TEXTFILE_DIR", "/var/lib/prometheus/node-exporter")
OUT = os.path.join(TEXTFILE_DIR, "llm_model.prom")


def get(path):
    with urllib.request.urlopen(LLM_URL + path, timeout=10) as r:
        return json.load(r)


def esc(v):
    return str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def slot_metrics():
    """Context-window usage per slot from /slots (absent if llama-server runs with --no-slots).

    n_prompt_tokens grows with every generated token (prompt + output so far) and stays at the
    cached conversation length after the request, so it is the number of tokens held in the slot.
    """
    try:
        slots = get("/slots")
    except Exception:
        return []
    out = [
        "# HELP llm_slot_context_tokens Tokens currently held in the slot context (prompt + generated).",
        "# TYPE llm_slot_context_tokens gauge",
    ]
    out += [f'llm_slot_context_tokens{{slot="{s.get("id", i)}"}} {s.get("n_prompt_tokens", 0)}'
            for i, s in enumerate(slots)]
    out += ["# HELP llm_slot_context_size Context size of the slot (tokens).",
            "# TYPE llm_slot_context_size gauge"]
    out += [f'llm_slot_context_size{{slot="{s.get("id", i)}"}} {s.get("n_ctx", 0)}' for i, s in enumerate(slots)]
    out += ["# HELP llm_slot_processing 1 while the slot is processing a request.",
            "# TYPE llm_slot_processing gauge"]
    out += [f'llm_slot_processing{{slot="{s.get("id", i)}"}} {int(bool(s.get("is_processing")))}'
            for i, s in enumerate(slots)]
    out += ["# HELP llm_slot_decoded_tokens Tokens generated so far in the running request.",
            "# TYPE llm_slot_decoded_tokens gauge"]
    out += [f'llm_slot_decoded_tokens{{slot="{s.get("id", i)}"}} '
            f'{((s.get("next_token") or [{}])[0] or {}).get("n_decoded", 0)}' for i, s in enumerate(slots)]
    return out


def main():
    lines = [
        "# HELP llm_server_up 1 if llama-server answered /props, else 0.",
        "# TYPE llm_server_up gauge",
    ]
    try:
        props = get("/props")
        models = get("/v1/models")
    except Exception:
        lines.append("llm_server_up 0")
    else:
        meta = (models.get("data") or [{}])[0].get("meta") or {}
        path = props.get("model_path", "")
        m = re.search(r"models--([^/]+)--([^/]+)/", path)
        labels = {
            "alias": props.get("model_alias", ""),
            "model_file": os.path.basename(path),
            "model_repo": f"{m.group(1)}/{m.group(2)}" if m else "",
            "quant": meta.get("ftype") or props.get("model_ftype", ""),
            "build": props.get("build_info", ""),
        }
        lab = ",".join(f'{k}="{esc(v)}"' for k, v in labels.items())
        gs = props.get("default_generation_settings") or {}
        lines += [
            "llm_server_up 1",
            "# HELP llm_model_info Model served by llama-server (value is always 1).",
            "# TYPE llm_model_info gauge",
            f"llm_model_info{{{lab}}} 1",
            "# HELP llm_model_context_size Configured context size (tokens).",
            "# TYPE llm_model_context_size gauge",
            f"llm_model_context_size {gs.get('n_ctx') or meta.get('n_ctx', 0)}",
            "# HELP llm_model_context_train Context size the model was trained for (tokens).",
            "# TYPE llm_model_context_train gauge",
            f"llm_model_context_train {meta.get('n_ctx_train', 0)}",
            "# HELP llm_model_slots Parallel slots (-np).",
            "# TYPE llm_model_slots gauge",
            f"llm_model_slots {props.get('total_slots', 0)}",
            "# HELP llm_model_parameters Model parameter count.",
            "# TYPE llm_model_parameters gauge",
            f"llm_model_parameters {meta.get('n_params', 0)}",
            "# HELP llm_model_size_bytes Model weights size in bytes.",
            "# TYPE llm_model_size_bytes gauge",
            f"llm_model_size_bytes {meta.get('size', 0)}",
            "# HELP llm_model_sleeping 1 if llama-server reports is_sleeping.",
            "# TYPE llm_model_sleeping gauge",
            f"llm_model_sleeping {int(bool(props.get('is_sleeping')))}",
        ]
        lines += slot_metrics()
    lines += [
        "# HELP llm_model_info_last_run_timestamp_seconds Last run of llm-model-info.",
        "# TYPE llm_model_info_last_run_timestamp_seconds gauge",
        f"llm_model_info_last_run_timestamp_seconds {int(time.time())}",
    ]
    fd, tmp = tempfile.mkstemp(dir=TEXTFILE_DIR, prefix=".llm_model.", suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, OUT)


if __name__ == "__main__":
    main()
