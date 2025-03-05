const express = require('express');
const promClient = require('prom-client');

const app = express();
const register = new promClient.Registry();

const trafficCounter = new promClient.Counter({
    name: 'pod_network_traffic_bytes_total',
    help: 'Total network traffic in bytes',
    labelNames: ['pod', 'namespace']
});
register.registerMetric(trafficCounter);

app.get('/metrics', async (req, res) => {
    res.set('Content-Type', register.contentType);
    res.end(await register.metrics());
});

app.listen(9100, () => console.log('Traffic grabber running on port 9100'));