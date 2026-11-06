#!/usr/bin/env python3
"""Generate the 'LLM Server Overview' Grafana dashboard ConfigMap (mr-do-observer)."""
import json
import sys

DS = {"type": "prometheus", "uid": "${datasource}"}
S = 'server="$server"'
RI = "$__rate_interval"
panels = []
_id = [0]


def nid():
    _id[0] += 1
    return _id[0]


def tgt(expr, legend="", ref="A", instant=False, fmt="time_series"):
    t = {"datasource": DS, "expr": expr, "legendFormat": legend, "refId": ref, "range": not instant, "instant": instant}
    if fmt != "time_series":
        t["format"] = fmt
    return t


def row(title, y):
    panels.append({"type": "row", "title": title, "id": nid(), "collapsed": False,
                   "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}, "panels": []})


def stat(title, x, y, w, h, targets, unit="none", decimals=None, steps=None, mappings=None,
         field=None, color_mode="value", text_mode="auto", desc="", graph=False, mn=None, mx=None):
    d = {"unit": unit, "mappings": mappings or [],
         "thresholds": {"mode": "absolute", "steps": steps or [{"color": "blue", "value": None}]},
         "color": {"mode": "thresholds"}}
    if decimals is not None:
        d["decimals"] = decimals
    if mn is not None:
        d["min"] = mn
    if mx is not None:
        d["max"] = mx
    panels.append({
        "type": "stat", "title": title, "id": nid(), "datasource": DS, "description": desc,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "fieldConfig": {"defaults": d, "overrides": []},
        "options": {"reduceOptions": {"values": False, "calcs": ["lastNotNull"], "fields": field or ""},
                    "colorMode": color_mode, "graphMode": "area" if graph else "none", "textMode": text_mode,
                    "justifyMode": "center", "orientation": "auto", "wideLayout": True, "showPercentChange": False},
        "targets": targets})


def gauge(title, x, y, w, h, targets, unit="percent", steps=None, mn=0, mx=100, desc=""):
    panels.append({
        "type": "gauge", "title": title, "id": nid(), "datasource": DS, "description": desc,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "fieldConfig": {"defaults": {"unit": unit, "min": mn, "max": mx, "color": {"mode": "thresholds"},
                                     "thresholds": {"mode": "absolute", "steps": steps or PCT}}, "overrides": []},
        "options": {"reduceOptions": {"values": False, "calcs": ["lastNotNull"], "fields": ""},
                    "showThresholdLabels": False, "showThresholdMarkers": True},
        "targets": targets})


def ts(title, x, y, w, h, targets, unit="none", overrides=None, mn=None, mx=None, desc="",
       stack=False, fill=10, decimals=None, legend_calcs=("mean", "max", "lastNotNull")):
    d = {"unit": unit, "color": {"mode": "palette-classic"},
         "custom": {"drawStyle": "line", "lineWidth": 2, "fillOpacity": fill, "showPoints": "never",
                    "spanNulls": False, "axisBorderShow": False, "lineInterpolation": "smooth",
                    "stacking": {"mode": "normal" if stack else "none", "group": "A"}},
         "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}]}}
    if mn is not None:
        d["min"] = mn
    if mx is not None:
        d["max"] = mx
    if decimals is not None:
        d["decimals"] = decimals
    panels.append({
        "type": "timeseries", "title": title, "id": nid(), "datasource": DS, "description": desc,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "fieldConfig": {"defaults": d, "overrides": overrides or []},
        "options": {"legend": {"displayMode": "table", "placement": "bottom", "showLegend": True,
                               "calcs": list(legend_calcs)},
                    "tooltip": {"mode": "multi", "sort": "none"}},
        "targets": targets})


def right_axis(name, unit=None):
    props = [{"id": "custom.axisPlacement", "value": "right"}]
    if unit:
        props.append({"id": "unit", "value": unit})
    return {"matcher": {"id": "byName", "options": name}, "properties": props}


def color(name, c):
    return {"matcher": {"id": "byName", "options": name},
            "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": c}}]}


PCT = [{"color": "green", "value": None}, {"color": "orange", "value": 75}, {"color": "red", "value": 90}]
TEMP = [{"color": "green", "value": None}, {"color": "orange", "value": 75}, {"color": "red", "value": 85}]
UPDOWN = [{"type": "value", "options": {"0": {"text": "DOWN", "color": "red", "index": 0},
                                        "1": {"text": "UP", "color": "green", "index": 1}}},
          {"type": "special", "options": {"match": "null", "result": {"text": "NO DATA", "color": "red", "index": 2}}}]
RED0 = [{"color": "red", "value": None}, {"color": "green", "value": 1}]

GEN_TPS = (f'rate(llamacpp:tokens_predicted_total{{{S}}}[{RI}]) / '
           f'rate(llamacpp:tokens_predicted_seconds_total{{{S}}}[{RI}])')
PP_TPS = (f'rate(llamacpp:prompt_tokens_total{{{S}}}[{RI}]) / '
          f'rate(llamacpp:prompt_seconds_total{{{S}}}[{RI}])')
THRU = f'rate(llamacpp:tokens_predicted_total{{{S}}}[{RI}])'
# Speculative-decoding acceptance: llama.cpp spec_decode_* counters, else Strata's strata:drafts_* (MTP or DFlash2).
def accept(fn, win):
    return (f'(100 * {fn}(llamacpp:spec_decode_num_accepted_tokens_total{{{S}}}[{win}]) / '
            f'{fn}(llamacpp:spec_decode_num_draft_tokens_total{{{S}}}[{win}])) or '
            f'(100 * {fn}(strata:drafts_accepted_total{{{S}}}[{win}]) / {fn}(strata:drafts_offered_total{{{S}}}[{win}]))')


MTP = accept('rate', RI)
# Context peak: llama.cpp n_tokens_max (since start), else (Strata) the max of the slot usage over the time range.
CTX_PEAK = (f'(100 * llamacpp:n_tokens_max{{{S}}} / on(server) llm_model_context_size{{{S}}}) or '
            f'(100 * max_over_time(sum by (server) (llm_slot_context_tokens{{{S}}})[$__range:]) / '
            f'on(server) sum by (server) (llm_slot_context_size{{{S}}}))')
INFO = f'llm_model_info{{{S}}}'
GPUINFO = f'nvidia_smi_gpu_info{{{S}}} or llm_gpu_info{{{S}}}'


def g(nv, amd):
    """Vendor-neutral GPU expression: NVIDIA exporter metric, else the llm_gpu_* (AMD sysfs) metric."""
    return f'({nv}) or ({amd})'

# ---------------------------------------------------------------- Model & status
y = 0
row("Model & status", y); y += 1
stat("Model (alias)", 0, y, 5, 4, [tgt(INFO, instant=True, fmt="table")], field="/^alias$/", color_mode="none",
     desc="Alias served by llama-server (from /props via llm-model-info, refreshed every 30 s).")
stat("Model file", 5, y, 7, 4, [tgt(INFO, instant=True, fmt="table")], field="/^model_file$/", color_mode="none",
     desc="GGUF file currently loaded.")
stat("Quant", 12, y, 3, 4, [tgt(INFO, instant=True, fmt="table")], field="/^quant$/", color_mode="none")
stat("Parameters", 15, y, 3, 4, [tgt(f'llm_model_parameters{{{S}}}', instant=True)], unit="short", decimals=1)
stat("Weights size", 18, y, 3, 4, [tgt(f'llm_model_size_bytes{{{S}}}', instant=True)], unit="bytes", decimals=1)
stat("Context (tokens)", 21, y, 3, 4, [tgt(f'llm_model_context_size{{{S}}}', instant=True)], unit="none",
     desc="Configured context size (-c).")
y += 4
stat("llama.cpp build", 4, y, 5, 4, [tgt(INFO, instant=True, fmt="table")], field="/^build$/", color_mode="none")
stat("llama-server", 0, y, 4, 4, [tgt(f'up{{job="llm-llamacpp",{S}}}', instant=True)], mappings=UPDOWN,
     steps=RED0, color_mode="background", desc="Prometheus scrape of llama-server /metrics.")
stat("Host uptime", 9, y, 5, 4, [tgt(f'node_time_seconds{{{S}}} - node_boot_time_seconds{{{S}}}', instant=True)],
     unit="s", decimals=0)
y += 4
stat("Generation t/s (now)", 0, y, 4, 4, [tgt(GEN_TPS, instant=True)], unit="none", decimals=1, graph=False,
     steps=[{"color": "red", "value": None}, {"color": "orange", "value": 15}, {"color": "green", "value": 30}],
     desc="Decode speed while generating (tokens / generation-seconds) over the last rate interval. "
          "Empty when idle.")
stat("Generation t/s (range avg)", 4, y, 4, 4,
     [tgt(f'increase(llamacpp:tokens_predicted_total{{{S}}}[$__range]) / '
          f'increase(llamacpp:tokens_predicted_seconds_total{{{S}}}[$__range])', instant=True)],
     decimals=1, steps=[{"color": "red", "value": None}, {"color": "orange", "value": 15},
                        {"color": "green", "value": 30}],
     desc="Average decode speed over the selected time range (benchmark reference: 42 t/s with MTP).")
stat("Prompt t/s (range avg)", 8, y, 4, 4,
     [tgt(f'increase(llamacpp:prompt_tokens_total{{{S}}}[$__range]) / '
          f'increase(llamacpp:prompt_seconds_total{{{S}}}[$__range])', instant=True)], decimals=0)
stat("Tokens generated (range)", 12, y, 4, 4,
     [tgt(f'increase(llamacpp:tokens_predicted_total{{{S}}}[$__range])', instant=True)], unit="short", decimals=1)
stat("Prompt tokens (range)", 16, y, 4, 4,
     [tgt(f'increase(llamacpp:prompt_tokens_total{{{S}}}[$__range])', instant=True)], unit="short", decimals=1,
     desc="Prompt tokens processed, excluding tokens reused from the prompt cache.")
stat("Draft acceptance (range)", 20, y, 4, 4,
     [tgt(accept('increase', '$__range'), instant=True)],
     unit="percent", decimals=0,
     steps=[{"color": "red", "value": None}, {"color": "orange", "value": 40}, {"color": "green", "value": 60}],
     desc="Share of draft tokens (llama.cpp MTP; Strata MTP or DFlash2) accepted by the target model.")
stat("Requests active", 14, y - 4, 5, 4, [tgt(f'llamacpp:requests_processing{{{S}}}', instant=True)],
     steps=[{"color": "text", "value": None}, {"color": "green", "value": 1}])
stat("Context peak", 19, y - 4, 5, 4,
     [tgt(CTX_PEAK, instant=True)],
     unit="percent", decimals=0, steps=PCT,
     desc="Largest sequence (prompt + generation) as % of the configured context: since start (llama.cpp) "
          "or within the selected time range (Strata, from /slots samples).")
y += 4

# ---------------------------------------------------------------- Tokens per second
row("Tokens per second", y); y += 1
ts("Tokens per second", 0, y, 16, 10, [
    tgt(GEN_TPS, "Generation t/s", "A"),
    tgt(THRU, "Effective throughput t/s", "B"),
    tgt(PP_TPS, "Prompt (prefill) t/s", "C"),
], unit="none", mn=0, decimals=1, overrides=[
    right_axis("Prompt (prefill) t/s"), color("Generation t/s", "green"),
    color("Effective throughput t/s", "blue"), color("Prompt (prefill) t/s", "orange")],
   desc="Generation t/s = decode speed while generating (gaps = idle). Effective throughput = generated tokens "
        "per wall-clock second (0 when idle). Prompt t/s on the right axis. llama.cpp exposes cumulative "
        "counters, so values are averages over the rate interval (>= 1 min).")
ts("Draft acceptance", 16, y, 8, 10, [tgt(MTP, "accepted %", "A")], unit="percent", mn=0, mx=100,
   decimals=0, desc="Accepted / drafted tokens (llama.cpp MTP; Strata MTP or DFlash2). Higher = bigger speed-up.")
y += 10
ts("Tokens per minute", 0, y, 12, 8, [
    tgt(f'60 * rate(llamacpp:tokens_predicted_total{{{S}}}[{RI}])', "generated", "A"),
    tgt(f'60 * rate(llamacpp:prompt_tokens_total{{{S}}}[{RI}])', "prompt", "B"),
    tgt(f'60 * rate(llamacpp:prompt_tokens_cached_total{{{S}}}[{RI}])', "prompt (from cache)", "C"),
], unit="short", mn=0, legend_calcs=("mean", "max", "sum"))
ts("Requests", 12, y, 12, 8, [
    tgt(f'llamacpp:requests_processing{{{S}}}', "processing", "A"),
    tgt(f'llamacpp:requests_deferred{{{S}}}', "deferred (queued)", "B"),
], unit="none", mn=0, decimals=0, legend_calcs=("mean", "max"))
y += 8

# ---------------------------------------------------------------- Context window
row("Context window", y); y += 1
CTX_TOK = f'sum by (server) (llm_slot_context_tokens{{{S}}})'
CTX_SIZE = f'sum by (server) (llm_slot_context_size{{{S}}})'
CTX_PCT = f'100 * {CTX_TOK} / {CTX_SIZE}'
gauge("Context window used (now)", 0, y, 6, 8, [tgt(CTX_PCT, instant=True)], steps=PCT,
      desc="Tokens held in the slot context (prompt + generated so far) / context size. Stays at the last "
           "conversation length after a request (kept for prompt caching). Sampled every 10 s from /slots.")
stat("Tokens in context", 6, y, 4, 4, [tgt(CTX_TOK, instant=True)], unit="none", decimals=0,
     desc="Tokens currently held in the slot context(s).")
stat("Tokens free", 10, y, 4, 4, [tgt(f'{CTX_SIZE} - {CTX_TOK}', instant=True)], unit="none", decimals=0,
     steps=[{"color": "red", "value": None}, {"color": "orange", "value": 4096}, {"color": "green", "value": 16384}],
     desc="Context size minus tokens in context.")
stat("Slot busy", 6, y + 4, 4, 4, [tgt(f'max by (server) (llm_slot_processing{{{S}}})', instant=True)],
     mappings=[{"type": "value", "options": {"0": {"text": "idle", "color": "text", "index": 0},
                                             "1": {"text": "generating", "color": "green", "index": 1}}}],
     steps=[{"color": "text", "value": None}], color_mode="value")
stat("Generated (running request)", 10, y + 4, 4, 4,
     [tgt(f'sum by (server) (llm_slot_decoded_tokens{{{S}}})', instant=True)], unit="none", decimals=0,
     desc="Tokens generated so far by the request in progress (0 when idle).")
ts("Context window usage", 14, y, 10, 8, [
    tgt(CTX_PCT, "used %", "A"),
    tgt(CTX_PEAK, "peak %", "B"),
], unit="percent", mn=0, decimals=1, legend_calcs=("mean", "max", "lastNotNull"),
   overrides=[color("used %", "green"), color("peak since start %", "orange")],
   desc="used % = tokens in context / context size (10 s samples). peak = largest sequence since llama-server start.")
y += 8

# ---------------------------------------------------------------- GPU
row("GPU", y); y += 1
stat("GPU", 0, y, 5, 4, [tgt(GPUINFO, instant=True, fmt="table")], field="/^name$/", color_mode="none")
stat("Driver", 5, y, 3, 4, [tgt(GPUINFO, instant=True, fmt="table")], field="/^driver_version$/",
     color_mode="none")
gauge("GPU utilisation", 8, y, 4, 4, [tgt('100 * ' + g(f'nvidia_smi_utilization_gpu_ratio{{{S}}}', f'llm_gpu_busy_ratio{{{S}}}'), instant=True)])
gauge("VRAM used", 12, y, 4, 4, [tgt('100 * ' + g(f'nvidia_smi_memory_used_bytes{{{S}}} / nvidia_smi_memory_total_bytes{{{S}}}',
                                                       f'llm_gpu_memory_used_bytes{{{S}}} / llm_gpu_memory_total_bytes{{{S}}}'),
                                     instant=True)],
      steps=[{"color": "green", "value": None}, {"color": "orange", "value": 95}, {"color": "red", "value": 98}],
      desc="llama.cpp preallocates model and KV cache, so a high, flat value (90 %+) is normal.")
gauge("GPU temperature", 16, y, 4, 4, [tgt(g(f'nvidia_smi_temperature_gpu{{{S}}}', f'llm_gpu_temperature_celsius{{{S},sensor="edge"}}'), instant=True)],
      unit="celsius", mx=100, steps=TEMP)
gauge("Power (% of limit)", 20, y, 4, 4,
      [tgt('100 * ' + g(f'nvidia_smi_power_draw_watts{{{S}}} / nvidia_smi_enforced_power_limit_watts{{{S}}}',
                        f'llm_gpu_power_draw_watts{{{S}}} / llm_gpu_power_limit_watts{{{S}}}'), instant=True)],
      steps=[{"color": "green", "value": None}, {"color": "orange", "value": 80}, {"color": "red", "value": 95}],
      desc="GPU power draw as % of the card's power limit (watts: GPU power panel below).")
y += 4
ts("GPU utilisation", 0, y, 12, 8, [
    tgt('100 * ' + g(f'nvidia_smi_utilization_gpu_ratio{{{S}}}', f'llm_gpu_busy_ratio{{{S}}}'), "GPU busy %", "A"),
    tgt('100 * ' + g(f'nvidia_smi_utilization_memory_ratio{{{S}}}', f'llm_gpu_memory_busy_ratio{{{S}}}'),
        "memory controller busy %", "B"),
], unit="percent", mn=0, mx=100)
ts("VRAM", 12, y, 12, 8, [
    tgt(g(f'nvidia_smi_memory_used_bytes{{{S}}}', f'llm_gpu_memory_used_bytes{{{S}}}'), "used", "A"),
    tgt(g(f'nvidia_smi_memory_total_bytes{{{S}}}', f'llm_gpu_memory_total_bytes{{{S}}}'), "total", "B"),
], unit="bytes", mn=0, fill=0)
y += 8
ts("GPU temperature", 0, y, 8, 8, [tgt(f'label_replace(nvidia_smi_temperature_gpu{{{S}}}, "sensor", "gpu", "", "") or '
                                         f'llm_gpu_temperature_celsius{{{S}}}', "{{sensor}} °C", "A")],
   unit="celsius", legend_calcs=("mean", "max"))
ts("GPU power", 8, y, 8, 8, [
    tgt(g(f'nvidia_smi_power_draw_watts{{{S}}}', f'llm_gpu_power_draw_watts{{{S}}}'), "draw", "A"),
    tgt(g(f'nvidia_smi_enforced_power_limit_watts{{{S}}}', f'llm_gpu_power_limit_watts{{{S}}}'), "limit", "B"),
], unit="watt", mn=0, fill=0, legend_calcs=("mean", "max"))
ts("GPU clocks", 16, y, 8, 8, [
    tgt(g(f'nvidia_smi_clocks_current_sm_clock_hz{{{S}}}', f'llm_gpu_clock_hz{{{S},clock="sm"}}'), "SM / graphics", "A"),
    tgt(g(f'nvidia_smi_clocks_current_memory_clock_hz{{{S}}}', f'llm_gpu_clock_hz{{{S},clock="memory"}}'), "memory", "B"),
], unit="hertz", mn=0, fill=0, legend_calcs=("mean", "max"))
y += 8

# ---------------------------------------------------------------- System
row("System", y); y += 1
CPU = f'100 * (1 - avg by (server) (rate(node_cpu_seconds_total{{{S},mode="idle"}}[{RI}])))'
MEM = f'100 * (1 - node_memory_MemAvailable_bytes{{{S}}} / node_memory_MemTotal_bytes{{{S}}})'
ROOTFS = f'{S},mountpoint="/",fstype!~"tmpfs|overlay"'
gauge("CPU", 0, y, 4, 4, [tgt(CPU, instant=True)])
gauge("RAM used", 4, y, 4, 4, [tgt(MEM, instant=True)])
stat("Swap used", 8, y, 4, 4, [tgt(f'node_memory_SwapTotal_bytes{{{S}}} - node_memory_SwapFree_bytes{{{S}}}',
                                    instant=True)], unit="bytes", decimals=1,
     steps=[{"color": "green", "value": None}, {"color": "orange", "value": 104857600},
            {"color": "red", "value": 1073741824}],
     desc="Swap in use. Any swap growth while benchmarking makes the benchmark invalid.")
gauge("Disk / used", 12, y, 4, 4, [tgt(f'100 * (1 - node_filesystem_avail_bytes{{{ROOTFS}}} / '
                                       f'node_filesystem_size_bytes{{{ROOTFS}}})', instant=True)])
stat("Load (1m / 16 threads)", 16, y, 4, 4, [tgt(f'node_load1{{{S}}}', instant=True)], decimals=2,
     steps=[{"color": "green", "value": None}, {"color": "orange", "value": 12}, {"color": "red", "value": 16}])
stat("CPU temperature (max)", 20, y, 4, 4,
     [tgt(f'max by (server) (node_hwmon_temp_celsius{{{S},chip=~".*coretemp.*"}})', instant=True)],
     unit="celsius", decimals=0, steps=TEMP)
y += 4
ts("CPU", 0, y, 12, 8, [
    tgt(f'100 * sum by (mode) (rate(node_cpu_seconds_total{{{S},mode!="idle"}}[{RI}])) / '
        f'scalar(count(node_cpu_seconds_total{{{S},mode="idle"}}))', "{{mode}}", "A"),
], unit="percent", mn=0, mx=100, stack=True, fill=40)
ts("Memory", 12, y, 12, 8, [
    tgt(f'node_memory_MemTotal_bytes{{{S}}} - node_memory_MemAvailable_bytes{{{S}}}', "used", "A"),
    tgt(f'node_memory_Cached_bytes{{{S}}} + node_memory_Buffers_bytes{{{S}}}', "cache + buffers", "B"),
    tgt(f'node_memory_MemTotal_bytes{{{S}}}', "total", "C"),
    tgt(f'node_memory_SwapTotal_bytes{{{S}}} - node_memory_SwapFree_bytes{{{S}}}', "swap used", "D"),
], unit="bytes", mn=0, fill=0)
y += 8
ts("Network", 0, y, 12, 8, [
    tgt(f'rate(node_network_receive_bytes_total{{{S},device!~"lo|veth.*|docker.*|br-.*|virbr.*|lxd.*"}}[{RI}])',
        "rx {{device}}", "A"),
    tgt(f'-rate(node_network_transmit_bytes_total{{{S},device!~"lo|veth.*|docker.*|br-.*|virbr.*|lxd.*"}}[{RI}])',
        "tx {{device}}", "B"),
], unit="Bps", desc="Receive up, transmit down.")
ts("Disk I/O", 12, y, 12, 8, [
    tgt(f'rate(node_disk_read_bytes_total{{{S},device=~"nvme[0-9]+n[0-9]+|sd[a-z]+"}}[{RI}])',
        "read {{device}}", "A"),
    tgt(f'-rate(node_disk_written_bytes_total{{{S},device=~"nvme[0-9]+n[0-9]+|sd[a-z]+"}}[{RI}])',
        "write {{device}}", "B"),
], unit="Bps", desc="Read up, write down.")
y += 8

dashboard = {
    "annotations": {"list": []},
    "description": "LLM server system overview: served model, tokens/s, GPU and host metrics. "
                   "Source: ElTabaco/mr-do-observer kubernetes/grafana/dashboard-llm-server-configmap.yml",
    "editable": True, "graphTooltip": 1, "id": None, "links": [], "panels": panels,
    "refresh": "30s", "schemaVersion": 39, "tags": ["llm", "llama.cpp", "gpu"],
    "templating": {"list": [
        {"name": "datasource", "label": "Data source", "type": "datasource", "query": "prometheus",
         "current": {"selected": True, "text": "Prometheus", "value": "Prometheus"}, "hide": 0,
         "refresh": 1, "options": [], "includeAll": False, "multi": False},
        {"name": "server", "label": "Server", "type": "query", "datasource": DS,
         "query": {"query": 'label_values(up{job=~"llm-.*"}, server)', "refId": "server"},
         "definition": 'label_values(up{job=~"llm-.*"}, server)', "refresh": 2, "sort": 1,
         "includeAll": False, "multi": False, "hide": 0, "current": {}, "options": []},
    ]},
    "time": {"from": "now-6h", "to": "now"}, "timepicker": {}, "timezone": "browser",
    "title": "LLM Server Overview", "uid": "llm-server-overview", "version": 1,
}

body = json.dumps(dashboard, indent=2, ensure_ascii=False)
out = ["apiVersion: v1", "kind: ConfigMap", "metadata:", "  name: grafana-dashboard-llm-server",
       "  namespace: monitoring", "  labels:", "    app: grafana", "data:", "  llm-server.json: |"]
out += ["    " + line for line in body.splitlines()]
sys.stdout.write("\n".join(out) + "\n")
