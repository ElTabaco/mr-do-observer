kubectl delete -f mr-do-observer-deployment.yml
kubectl delete -f mr-do-observer-service.yml
kubectl delete configmap mr-do-asound-cfgmap -n mr-do-observer
# kubectl delete configmap mr-do-kodi-cfgmap -n mr-do-observer
kubectl delete configmap mr-do-snapserver-cfgmap -n mr-do-observer
kubectl delete -f mr-do-observer-pvc.yml
kubectl delete -f mr-do-observer-pv.yml
# kubectl delete -f mr-do-observer-ingress.yml
# kubectl delete all,deployment,configmap,pv,pvc --all -n mr-do-observer
kubectl delete namespace mr-do-observer
