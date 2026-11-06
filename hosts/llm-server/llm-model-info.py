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


def amd_gpu_metrics():
    """Vendor-neutral llm_gpu_* metrics for AMD discrete GPUs from amdgpu sysfs (NVIDIA uses nvidia_gpu_exporter).

    Integrated GPUs and non-AMD cards are skipped. Name/arch from `amd-smi static --asic` when available.
    """
    import glob
    import subprocess

    def rds(path):
        try:
            with open(path) as f:
                return f.read().strip()
        except OSError:
            return None

    def rd(path):
        try:
            return float(rds(path) or "")
        except ValueError:
            return None

    asic = {}
    try:
        out = subprocess.run(["amd-smi", "static", "--asic", "--json"], capture_output=True, text=True, timeout=5)
        for g in json.loads(out.stdout).get("gpu_data", []):
            a = g.get("asic") or {}
            asic[str(a.get("device_id", "")).lower()] = a
    except Exception:
        pass
    series = {k: [] for k in ("info", "busy", "membusy", "used", "total", "temp", "power", "cap", "clock", "fan")}
    idx = 0
    for card in sorted(glob.glob("/sys/class/drm/card[0-9]*")):
        dev = os.path.join(card, "device")
        if not re.fullmatch(r"card\d+", os.path.basename(card)) or rds(f"{dev}/vendor") != "0x1002":
            continue
        total = rd(f"{dev}/mem_info_vram_total")
        if not total or total < 4 * 2**30:  # skip APUs / iGPUs (small carve-out)
            continue
        gpu = f'gpu="{idx}"'
        idx += 1
        devid = rds(f"{dev}/device") or ""
        a = asic.get(devid.lower(), {})
        name = a.get("market_name") or f"AMD {devid}"
        series["info"].append(f'llm_gpu_info{{{gpu},name="{esc(name)}",driver_version="amdgpu {esc(os.uname().release)}",'
                              f'arch="{esc(a.get("target_graphics_version", ""))}",'
                              f'pci="{esc(os.path.basename(os.path.realpath(dev)))}"}} 1')
        for key, f in (("busy", "gpu_busy_percent"), ("membusy", "mem_busy_percent")):
            v = rd(f"{dev}/{f}")
            if v is not None:
                series[key].append(f"{{{gpu}}} {v / 100}")
        series["total"].append(f"{{{gpu}}} {int(total)}")
        used = rd(f"{dev}/mem_info_vram_used")
        if used is not None:
            series["used"].append(f"{{{gpu}}} {int(used)}")
        for hw in glob.glob(f"{dev}/hwmon/hwmon*"):
            for t in sorted(glob.glob(f"{hw}/temp*_input")):
                v = rd(t)
                label = rds(t.replace("_input", "_label")) or os.path.basename(t)[:-6]
                if v is not None:
                    series["temp"].append(f'{{{gpu},sensor="{esc(label)}"}} {v / 1000}')
            p = rd(f"{hw}/power1_average")
            p = p if p is not None else rd(f"{hw}/power1_input")
            if p is not None:
                series["power"].append(f"{{{gpu}}} {p / 1e6}")
            c = rd(f"{hw}/power1_cap")
            if c is not None:
                series["cap"].append(f"{{{gpu}}} {c / 1e6}")
            for n, clk in (("1", "sm"), ("2", "memory")):
                v = rd(f"{hw}/freq{n}_input")
                if v is not None:
                    series["clock"].append(f'{{{gpu},clock="{clk}"}} {int(v)}')
            v = rd(f"{hw}/fan1_input")
            if v is not None:
                series["fan"].append(f"{{{gpu}}} {int(v)}")
    meta = {
        "info": ("llm_gpu_info", "GPU identity (value is always 1)."),
        "busy": ("llm_gpu_busy_ratio", "GPU busy (0-1)."),
        "membusy": ("llm_gpu_memory_busy_ratio", "Memory controller busy (0-1)."),
        "used": ("llm_gpu_memory_used_bytes", "VRAM used."),
        "total": ("llm_gpu_memory_total_bytes", "VRAM total."),
        "temp": ("llm_gpu_temperature_celsius", "GPU temperature per sensor (edge, junction, mem)."),
        "power": ("llm_gpu_power_draw_watts", "GPU power draw (average)."),
        "cap": ("llm_gpu_power_limit_watts", "GPU power limit."),
        "clock": ("llm_gpu_clock_hz", "Current clock (sm = graphics, memory)."),
        "fan": ("llm_gpu_fan_rpm", "Fan speed."),
    }
    out = []
    for key, rows in series.items():
        if not rows:
            continue
        mname, help_ = meta[key]
        out += [f"# HELP {mname} {help_}", f"# TYPE {mname} gauge"]
        out += rows if key == "info" else [mname + r for r in rows]
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
        first = (models.get("data") or [{}])[0]
        meta = first.get("meta") or {}
        path = props.get("model_path", "")
        m = re.search(r"models--([^/]+)--([^/]+)/", path)
        labels = {
            # Strata lists the configured name (llama.cpp --alias equivalent) in "aliases"
            "alias": (first.get("aliases") or [None])[0] or props.get("model_alias", ""),
            "model_file": os.path.basename(path),
            "model_repo": f"{m.group(1)}/{m.group(2)}" if m else "",
            "quant": (q.group(1) if (q := re.search(r"((?:UD-)?I?Q\d[\w]*?)(?:-\d{5}-of-\d{5})?\.gguf$", path))
                      else meta.get("ftype") or props.get("model_ftype", "")),
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
            "# HELP llm_model_slots Parallel slots (-np).",
            "# TYPE llm_model_slots gauge",
            f"llm_model_slots {props.get('total_slots', 0)}",
            "# HELP llm_model_sleeping 1 if llama-server reports is_sleeping.",
            "# TYPE llm_model_sleeping gauge",
            f"llm_model_sleeping {int(bool(props.get('is_sleeping')))}",
        ]
        # Only what the engine reports: Strata's /v1/models has no n_ctx_train/n_params/size -> series absent
        # ("No data" in Grafana) instead of a misleading 0.
        for name, key, help_ in (("llm_model_context_train", "n_ctx_train", "Context size the model was trained for (tokens)."),
                                 ("llm_model_parameters", "n_params", "Model parameter count."),
                                 ("llm_model_size_bytes", "size", "Model weights size in bytes.")):
            if meta.get(key):
                lines += [f"# HELP {name} {help_}", f"# TYPE {name} gauge", f"{name} {meta[key]}"]
        lines += slot_metrics()
    lines += amd_gpu_metrics()
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
