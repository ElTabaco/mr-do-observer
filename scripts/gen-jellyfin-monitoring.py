#!/usr/bin/env python3
"""Generate the Grafana provisioning for mr-jellyfin (namespace mr-do-jellyfin):

  kubernetes/grafana/alerting-configmap.yml          contact point "callmebot" + rule group "mr-jellyfin"
  kubernetes/grafana/dashboard-jellyfin-configmap.yml dashboard "Jellyfin" (folder Media)

Alert rules use simplified routing (rule-level notification_settings.receiver), so the
organisation's notification policy tree is not touched. Metrics: kube-state-metrics, cAdvisor,
the pod scrape (job kubernetes-pods, port = jellyfin_exporter 9594) and jellyfin_exporter v1.6.0
(collectors media, playing, system, users, transcoding, tasks, storage).

Run from the repo root: python3 scripts/gen-jellyfin-monitoring.py
"""
import json
from pathlib import Path

DS = {"type": "prometheus", "uid": "PBFA97CFB590B2093"}
NS = 'namespace="mr-do-jellyfin"'
RELAY = "http://callmebot-relay.monitoring.svc.cluster.local:8080/alert"

# ---------------------------------------------------------------------------------------------
# Alert rules: (uid, title, expr, op, threshold, for, noData, severity, summary, description)
# The expression must return one series (aggregated); the rule fires when "value op threshold".
RULES = [
    ("jf-down", "JellyfinDown",
     f'1 - min(up{{{NS}, app="mr-do-jellyfin"}} or jellyfin_up{{{NS}}})', "gt", 0, "5m", "Alerting", "critical",
     "Jellyfin is down or not answering its API",
     "Pod scrape or jellyfin_up failed for 5 min. kubectl -n mr-do-jellyfin get pods; "
     "scripts/healthcheck.sh; docs/troubleshooting.md"),
    ("jf-unavailable", "JellyfinNotAvailable",
     f'1 - min(kube_deployment_status_replicas_available{{{NS}, deployment="mr-do-jellyfin"}})', "gt", 0, "10m",
     "Alerting", "critical",
     "Jellyfin deployment has no ready replica",
     "Preflight failed (NFS/NAS), probes failing or GPU resource missing. "
     "kubectl -n mr-do-jellyfin describe pod -l app=mr-do-jellyfin"),
    ("jf-restarts", "JellyfinRestarting",
     f'sum(increase(kube_pod_container_status_restarts_total{{{NS}}}[1h]))', "gt", 2, "0s", "OK", "warning",
     "Containers in mr-do-jellyfin restarted more than twice in 1 h",
     "kubectl -n mr-do-jellyfin get pods; logs --previous of the restarting container"),
    ("jf-pvc", "JellyfinPVCNotBound",
     f'sum(kube_persistentvolumeclaim_status_phase{{{NS}, phase!="Bound"}})', "gt", 0, "5m", "OK", "critical",
     "A Jellyfin PVC is not Bound",
     "kubectl -n mr-do-jellyfin get pvc; kubectl get pv | grep mr-do-jellyfin"),
    ("jf-nas", "JellyfinMediaStorageUnreadable",
     f'1 - min(jellyfin_scrape_collector_success{{{NS}, collector="storage"}})', "gt", 0, "10m", "OK", "critical",
     "Jellyfin cannot read its storage paths (NAS / NFS?)",
     "The exporter's storage collector fails for 10 min. Check the NAS (riemerkNASS, 192.168.0.233) "
     "and the NFS mount: kubectl -n mr-do-jellyfin exec deploy/mr-do-jellyfin -- ls /media"),
    ("jf-nas-space", "JellyfinMediaStorageLow",
     f'min(jellyfin_storage_free_bytes{{{NS}, location="library"}} / (jellyfin_storage_free_bytes{{{NS}, location="library"}}'
     f' + jellyfin_storage_used_bytes{{{NS}, location="library"}}))', "lt", 0.1, "30m", "OK", "warning",
     "Media storage on the NAS has less than 10% free",
     "USB SSD share usbmedia on the NAS; free space or move media"),
    ("jf-local-space", "JellyfinLocalStorageLow",
     f'min(jellyfin_storage_free_bytes{{{NS}, location=~"program_data|cache|transcodes"}} / (jellyfin_storage_free_bytes{{{NS}, location=~"program_data|cache|transcodes"}}'
     f' + jellyfin_storage_used_bytes{{{NS}, location=~"program_data|cache|transcodes"}}))', "lt", 0.1, "30m", "OK", "warning",
     "Jellyfin config/cache/transcode storage has less than 10% free",
     "mr2 /var/lib/mr-jellyfin (NVMe) or the transcode emptyDir"),
    ("jf-memory", "JellyfinMemoryHigh",
     f'max(sum by (pod) (container_memory_working_set_bytes{{{NS}, container="jellyfin"}}) / '
     f'sum by (pod) (kube_pod_container_resource_limits{{{NS}, container="jellyfin", resource="memory"}}))',
     "gt", 0.9, "15m", "OK", "warning",
     "Jellyfin uses more than 90% of its memory limit",
     "Risk of OOM kill; check active transcodes"),
    ("jf-cpu", "JellyfinCPUThrottled",
     f'max(sum by (pod) (rate(container_cpu_cfs_throttled_periods_total{{{NS}, container="jellyfin"}}[5m])) / '
     f'sum by (pod) (rate(container_cpu_cfs_periods_total{{{NS}, container="jellyfin"}}[5m])))',
     "gt", 0.5, "15m", "OK", "warning",
     "Jellyfin CPU is throttled in more than 50% of periods",
     "Likely software transcoding (VP8/MPEG-2/VC-1 sources, or GPU not used): docs/hardware-compatibility.md"),
    ("jf-backup-failed", "JellyfinBackupFailed",
     f'sum(kube_job_status_failed{{{NS}, job_name=~"mr-do-jellyfin-backup.*"}})', "gt", 0, "0s", "OK", "critical",
     "A Jellyfin backup job failed",
     "kubectl -n mr-do-jellyfin get jobs; logs of the failed job; docs/backup-recovery.md"),
    ("jf-backup-missing", "JellyfinBackupMissing",
     f'time() - max(kube_cronjob_status_last_successful_time{{{NS}, cronjob="mr-do-jellyfin-backup"}})',
     "gt", 26 * 3600, "30m", "OK", "critical",
     "No successful Jellyfin backup for more than 26 hours",
     "Daily CronJob 03:15; run scripts/backup.sh and check its log"),
    ("jf-epg", "JellyfinGuideGrabberDown",
     f'1 - min(kube_deployment_status_replicas_available{{{NS}, deployment="mr-do-jellyfin-epg"}})', "gt", 0, "30m",
     "OK", "warning",
     "Live TV guide grabber (mr-do-jellyfin-epg) not ready",
     "Programme guide will run out after 3 days. kubectl -n mr-do-jellyfin logs deploy/mr-do-jellyfin-epg"),
    ("jf-gpu-plugin", "JellyfinGPUDevicePluginDown",
     'min(kube_daemonset_status_number_ready{namespace="kube-system", daemonset="generic-device-plugin"})',
     "lt", 1, "10m", "Alerting", "warning",
     "GPU device plugin on mr2 not ready",
     "Jellyfin cannot be (re)scheduled with the GPU. kubectl -n kube-system get pods -l "
     "app.kubernetes.io/name=generic-device-plugin"),
]


def rule(uid, title, expr, op, thr, for_, nodata, sev, summary, desc):
    return {
        "uid": uid,
        "title": title,
        "condition": "C",
        "data": [
            {"refId": "A", "relativeTimeRange": {"from": 900, "to": 0}, "datasourceUid": DS["uid"],
             "model": {"refId": "A", "expr": expr, "instant": True, "range": False,
                       "intervalMs": 15000, "maxDataPoints": 43200}},
            {"refId": "C", "relativeTimeRange": {"from": 0, "to": 0}, "datasourceUid": "__expr__",
             "model": {"refId": "C", "type": "threshold", "expression": "A",
                       "conditions": [{"evaluator": {"type": op, "params": [thr]}}]}},
        ],
        "for": for_,
        "noDataState": nodata,
        "execErrState": "Error",
        "labels": {"severity": sev, "project": "mr-jellyfin"},
        "annotations": {"summary": summary, "description": desc},
        "isPaused": False,
        "notification_settings": {"receiver": "callmebot", "group_by": ["alertname"],
                                  "repeat_interval": "12h"},
    }


alerting = {
    "apiVersion": 1,
    "contactPoints": [{
        "orgId": 1,
        "name": "callmebot",
        "receivers": [{"uid": "callmebot-relay", "type": "webhook", "disableResolveMessage": False,
                       "settings": {"url": RELAY, "httpMethod": "POST"}}],
    }],
    "groups": [{"orgId": 1, "name": "mr-jellyfin", "folder": "Jellyfin", "interval": "1m",
                "rules": [rule(*r) for r in RULES]}],
}

# ---------------------------------------------------------------------------------------------
# Dashboard
_id = 0


def pid():
    global _id
    _id += 1
    return _id


def target(expr, legend="", instant=False, fmt=None):
    t = {"datasource": DS, "expr": expr, "legendFormat": legend, "refId": chr(64 + pid() % 26 or 1)}
    if instant:
        t["instant"] = True
        t["range"] = False
    if fmt:
        t["format"] = fmt
    return t


def stat(title, expr, x, y, w=4, unit="none", thresholds=None, mappings=None, decimals=None):
    p = {"type": "stat", "title": title, "datasource": DS, "id": pid(),
         "gridPos": {"x": x, "y": y, "w": w, "h": 4},
         "targets": [target(expr, instant=True)],
         "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "background",
                     "graphMode": "none", "textMode": "value"},
         "fieldConfig": {"defaults": {"unit": unit, "mappings": mappings or [],
                                      "thresholds": {"mode": "absolute",
                                                     "steps": thresholds or [{"color": "blue", "value": None}]}},
                         "overrides": []}}
    if decimals is not None:
        p["fieldConfig"]["defaults"]["decimals"] = decimals
    return p


def ts(title, targets, x, y, w=12, h=8, unit="none", stack=False):
    return {"type": "timeseries", "title": title, "datasource": DS, "id": pid(),
            "gridPos": {"x": x, "y": y, "w": w, "h": h}, "targets": targets,
            "fieldConfig": {"defaults": {"unit": unit, "custom": {
                "fillOpacity": 15, "lineWidth": 1, "showPoints": "never",
                "stacking": {"mode": "normal" if stack else "none"}}}, "overrides": []},
            "options": {"legend": {"displayMode": "list", "placement": "bottom"},
                        "tooltip": {"mode": "multi"}}}


def table(title, expr, x, y, w, h, columns):
    return {"type": "table", "title": title, "datasource": DS, "id": pid(),
            "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "targets": [target(expr, instant=True, fmt="table")],
            "transformations": [{"id": "organize", "options": {
                "excludeByName": {"Time": True, "Value": True},
                "indexByName": {c: i for i, c in enumerate(columns)}}},
                {"id": "filterFieldsByName", "options": {"include": {"names": columns}}}],
            "options": {"showHeader": True}, "fieldConfig": {"defaults": {}, "overrides": []}}


UPDOWN = [{"type": "value", "options": {"0": {"text": "DOWN", "color": "red"},
                                        "1": {"text": "UP", "color": "green"}}}]
RG = [{"color": "red", "value": None}, {"color": "green", "value": 1}]
POD = f'{NS}, pod=~"mr-do-jellyfin-[a-z0-9]+-[a-z0-9]+"'

panels = [
    stat("Jellyfin", f'min(up{{{NS}, app="mr-do-jellyfin"}} or jellyfin_up{{{NS}}})', 0, 0,
         thresholds=RG, mappings=UPDOWN),
    stat("Playing now", f'count(jellyfin_now_playing_state{{{NS}}}) or vector(0)', 4, 0),
    stat("Transcoding now", f'max(jellyfin_transcoding_sessions{{{NS}}}) or vector(0)', 8, 0),
    stat("Restarts (24 h)", f'sum(increase(kube_pod_container_status_restarts_total{{{NS}}}[24h]))', 12, 0,
         thresholds=[{"color": "green", "value": None}, {"color": "orange", "value": 1},
                     {"color": "red", "value": 3}], decimals=0),
    stat("Last backup", f'time() - max(kube_cronjob_status_last_successful_time{{{NS}, cronjob="mr-do-jellyfin-backup"}})',
         16, 0, unit="s", thresholds=[{"color": "green", "value": None}, {"color": "red", "value": 93600}]),
    stat("GPU device plugin",
         'min(kube_daemonset_status_number_ready{namespace="kube-system", daemonset="generic-device-plugin"})',
         20, 0, thresholds=RG, mappings=UPDOWN),
    ts("Sessions", [target(f'count(jellyfin_now_playing_state{{{NS}}}) or vector(0)', "playing"),
                    target(f'max(jellyfin_transcoding_sessions{{{NS}}}) or vector(0)', "transcoding")], 0, 4),
    ts("CPU (cores)", [target(f'sum by (container) (rate(container_cpu_usage_seconds_total{{{NS}, container!="", container!="POD"}}[5m]))',
                              "{{container}}")], 12, 4),
    ts("Memory (working set)", [target(f'sum by (container) (container_memory_working_set_bytes{{{NS}, container!="", container!="POD"}})',
                                       "{{container}}")], 0, 12, unit="bytes"),
    ts("Network (Jellyfin pod)", [
        target(f'sum(rate(container_network_transmit_bytes_total{{{POD}}}[2m])) * 8', "out (to clients)"),
        target(f'sum(rate(container_network_receive_bytes_total{{{POD}}}[2m])) * 8', "in (NAS, streams)")],
       12, 12, unit="bps"),
    ts("CPU throttling (jellyfin)", [target(
        f'sum(rate(container_cpu_cfs_throttled_periods_total{{{NS}, container="jellyfin"}}[5m])) / '
        f'sum(rate(container_cpu_cfs_periods_total{{{NS}, container="jellyfin"}}[5m]))', "throttled share")],
       0, 20, unit="percentunit"),
    ts("Storage free", [target(
        f'jellyfin_storage_free_bytes{{{NS}, location=~"library|program_data|cache|transcodes"}} / '
        f'(jellyfin_storage_free_bytes{{{NS}, location=~"library|program_data|cache|transcodes"}} + '
        f'jellyfin_storage_used_bytes{{{NS}, location=~"library|program_data|cache|transcodes"}})', "{{name}}")],
       12, 20, unit="percentunit"),
    table("Active transcodes", f'jellyfin_transcoding_session_info{{{NS}}}', 0, 28, 24, 6,
          ["username", "device", "client", "title", "video_codec", "audio_codec", "hardware_acceleration",
           "method", "container"]),
    table("Now playing", f'jellyfin_now_playing_state{{{NS}}}', 0, 34, 24, 6,
          ["username", "device", "type", "title", "series_title", "method"]),
    ts("Library items", [target(f'jellyfin_media_count{{{NS}}}', "{{type}}")], 0, 40, w=12, h=7),
    table("PVCs", f'kube_persistentvolumeclaim_status_phase{{{NS}}} == 1', 12, 40, 12, 7,
          ["persistentvolumeclaim", "phase"]),
]

dashboard = {
    "title": "Jellyfin", "uid": "mr-jellyfin", "tags": ["jellyfin", "media"], "timezone": "browser",
    "editable": True, "schemaVersion": 39, "time": {"from": "now-6h", "to": "now"}, "refresh": "30s",
    "annotations": {"list": []}, "links": [], "templating": {"list": []}, "panels": panels,
    "description": "mr-jellyfin (namespace mr-do-jellyfin): availability, sessions, transcoding, "
                   "resources, storage, backup. Generated by scripts/gen-jellyfin-monitoring.py. "
                   "GPU engine load is not exported (gpu_busy_percent does not cover the VCN video engine).",
}


def configmap(name, key, text, comment):
    body = "\n".join("    " + ln if ln else "" for ln in text.splitlines())
    return (f"# {comment}\n# Generated by scripts/gen-jellyfin-monitoring.py - edit the script, not this file.\n"
            f"apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: {name}\n  namespace: monitoring\n"
            f"  labels:\n    app: grafana\ndata:\n  {key}: |\n{body}\n")


def to_yaml(obj):
    # JSON is valid YAML; Grafana's provisioning reader accepts it.
    return json.dumps(obj, indent=2, ensure_ascii=False)


root = Path(__file__).resolve().parent.parent / "kubernetes" / "grafana"
(root / "alerting-configmap.yml").write_text(configmap(
    "grafana-alerting", "mr-jellyfin.yaml", to_yaml(alerting),
    "Grafana alerting provisioning: contact point callmebot (-> callmebot-relay) + mr-jellyfin rules."))
(root / "dashboard-jellyfin-configmap.yml").write_text(configmap(
    "grafana-dashboard-jellyfin", "jellyfin.json", json.dumps(dashboard, indent=2, ensure_ascii=False),
    "Grafana dashboard Jellyfin (folder Media)."))
print(f"{len(RULES)} rules, {len(panels)} panels written")
