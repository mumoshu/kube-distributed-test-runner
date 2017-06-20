#!/bin/bash
set -e

# Build for linux-amd64 docker containers on alpine
export CGO_ENABLED=1
export GOOS=linux
export GOARCH=amd64

kubectl_dir=/usr/local/bin
if ! [ -f rootfs$kubectl_dir/kubectl ]; then
  if ! [ -f kubernetes-client/kubernetes/client/bin/kubectl ]; then
    echo "Downloading kubectl..."
    mkdir -p kubernetes-client
    pushd kubernetes-client > /dev/null
    curl -L -o - https://dl.k8s.io/v1.6.4/kubernetes-client-linux-amd64.tar.gz | tar zxvf -
    popd > /dev/null
  fi
  
  rm -Rf rootfs$kubectl_dir
  mkdir -p rootfs$kubectl_dir
  mv kubernetes-client/kubernetes/client/bin/kubectl rootfs$kubectl_dir/kubectl
  rm -Rf kubernetes-client/*
fi

echo "Building smuggler..."
gopath=$(pwd)/gopath/
gopkg=$gopath/src/github.com/redfactorlabs/concourse-smuggler-resource
mkdir -p $gopath
if ! test -d $gopkg; then
  git clone git@github.com:redfactorlabs/concourse-smuggler-resource.git $gopkg
fi
pushd $gopkg > /dev/null
GOPATH=$gopath godep restore
GOPATH=$gopath ./scripts/build
popd > /dev/null

mkdir -p ./rootfs/opt/resource
cp $gopkg/assets/smuggler-linux-amd64 ./rootfs/opt/resource/smuggler

echo "Building container..."
CONTAINER_TAG=${CONTAINER_TAG:-mumoshu/concourse-kube-broker-resource}
docker build -t ${CONTAINER_TAG} .
docker push ${CONTAINER_TAG}

echo "${CONTAINER_TAG} ready to use"
