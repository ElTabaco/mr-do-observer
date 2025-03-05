# mr-do-observer

Simple observer to monitor kubernetes pods and application running in this pods


## Used tools

* [Prometheus](https://prometheus.io/)
* [Grafana](https://grafana.com/)
* [Docker](https://docs.docker.com/get-started/docker-concepts/building-images/build-tag-and-publish-an-image/js) and [JavaScript](https://www.javascript.com/) for custom grabber


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
