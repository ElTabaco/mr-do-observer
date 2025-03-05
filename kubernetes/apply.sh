kubectl create namespace mr-do-observer
# Apply ServiceMonitor CRD
kubectl apply -f https://raw.githubusercontent.com/prometheus-operator/prometheus-operator/main/example/prometheus-operator-crd/monitoring.coreos.com_servicemonitors.yaml  -n mr-do-observer

kubectl apply -f mr-do-observer-pv.yml
kubectl apply -f mr-do-observer-pvc.yml
kubectl create configmap mr-do-snapserver-cfgmap --from-file=etc/snapserver.conf -n mr-do-observer
# kubectl get configmap mr-do-snapserver-cfgmap -o yaml  -n mr-do-observer
kubectl create configmap mr-do-asound-cfgmap --from-file=etc/asound.conf -n mr-do-observer
# kubectl get configmap mr-do-asound-cfgmap -o yaml  -n mr-do-observer
kubectl apply -f mr-do-observer-service.yml
kubectl apply -f mr-do-observer-deployment.yml
# kubectl apply -f mr-do-observer-ingress.yml

kubectl describe pod mr-do-observer -n mr-do-observer
kubectl get pods -n mr-do-observer -o wide
kubectl get pods --all-namespaces -o wide

# kubectl get ingress --all-namespaces -o wide
# kubectl describe ingress -n mr-do-observer

kubectl get pv --all-namespaces -o wide
kubectl get pvc --all-namespaces -o wide
kubectl describe pv mr-do-observer-pv-data -n mr-do-observer
kubectl describe pvc mr-do-observer-pvc-data -n mr-do-observer

kubectl get configmap --all-namespaces -o wide
kubectl get svc --all-namespaces
kubectl get services  -n mr-do-observer -o wide
kubectl describe services mr-do-observer-service -n mr-do-observer

kubectl get all -n mr-do-observer

echo Verify the CRD is installed
kubectl get crd servicemonitors.monitoring.coreos.com
