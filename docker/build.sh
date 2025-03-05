#!/bin/bash
set -euo pipefail
VERSION=0.0.0
ARCH=arm64
echo ${ARCH}
echo ${VERSION}

docker buildx build -t riemerk/mr-do-observer --build-arg ARCH=${ARCH} .
docker tag riemerk/mr-do-observer:latest riemer/mr-do-observer:${VERSION}-${ARCH}
