# mr-do-observer

Simple observer to monitor kubernetes pods and application running in this pods


## Used tools

* [Prometheus](https://prometheus.io/)
* [Grafana](https://grafana.com/)
* [Docker](https://docs.docker.com/get-started/docker-concepts/building-images/build-tag-and-publish-an-image/js) and [JavaScript](https://www.javascript.com/) for custom grabber

## Config

* Prometheus data source URL field:
  ```
  http://prometheus-service.mr-do-observer.svc.cluster.local:9090
  ```

## TODOs

- <input type="checkbox" disabled checked /> RUN Prometheus & Grafane on premis (kubernetes)
- <input type="checkbox" checked /> RUN PoC Custom grabber to monitor pod communication
- <input type="checkbox" disabled /> Create own dashboard for each pod. Configuration shall be in yaml files
  - <input type="checkbox" disabled /> Dashboard for mr-do-openhab
  - <input type="checkbox" disabled /> Dashboard for mr-do-teddycloud
  - <input type="checkbox" disabled /> Dashboard for mr-do-player
- <input type="checkbox" disabled /> Modify grabber to run as es service
- <input type="checkbox" disabled /> Exstend dashboards to monitor own applications
- <input type="checkbox" disabled /> Exstend dashboards to monitor own applications timings

## Cleanup

- <input type="checkbox" disabled /> Remove ServiceMonitor CRD  yaml file and use helm or script instead
  - ServiceMonitor CRD runs directly on the Kubernetes cluster, let’s install the CRDs and the Prometheus Operator directly via YAML.
     ```shell
    kubectl apply -f https://raw.githubusercontent.com/prometheus-operator/prometheus-operator/main/example/prometheus-operator-crd/monitoring.coreos.com_servicemonitors.yaml -n my-namespace
    ```
  - or helm.
     ```shell
    helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
    helm repo update
    helm install prometheus-operator prometheus-community/kube-prometheus-stack --namespace monitoring --create-namespace
    ```
