# Prometheus Scrape Configuration Example

In your Prometheus configuration (typically in prometheus.yml), add a new scrape job similar to the following:

``` yml
scrape_configs:
  - job_name: 'kube-state-metrics'
    kubernetes_sd_configs:
      - role: endpoints
        namespaces:
          names:
            - kube-system
    relabel_configs:
      # Keep only endpoints from the kube-state-metrics service with port "http-metrics"
      - source_labels: [__meta_kubernetes_service_name, __meta_kubernetes_endpoint_port_name]
        action: keep
        regex: kube-state-metrics;http-metrics
```

## Explanation

* Job Name:

  The job is named kube-state-metrics so that you can easily identify it in Prometheus.

* Kubernetes Service Discovery (kubernetes_sd_configs):
  
  The configuration tells Prometheus to discover endpoints from the Kubernetes API.

    * role: endpoints specifies that Prometheus should look for service endpoints.

    * The namespaces block restricts the discovery to the kube-system namespace (where kube‑state‑metrics is deployed).

* Relabeling:

  The relabel_configs section uses two labels:

    * __meta_kubernetes_service_name – which holds the name of the service.

    * __meta_kubernetes_endpoint_port_name – which holds the name of the port.

  The regex kube-state-metrics;http-metrics ensures that only endpoints from the kube-state-metrics service with the port name http-metrics are kept. This way, Prometheus scrapes only the desired metrics endpoint.