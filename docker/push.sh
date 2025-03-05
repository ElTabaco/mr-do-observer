#!/bin/bash
VERSION=27
ARCH=arm64

echo ${ARCH}
echo ${VERSION}

#docker image push --all-tags riemerk/mr-do-observer
docker login -u "myusername" -p "mypassword" docker.io
docker push riemerk/mr-do-observer:latest
docker push riemerk/mr-do-observer:${VERSION}-ARCH=${ARCH}
