#!/bin/bash

set -vxe

make docker-images
kubectl delete secret kubedt-pytest{,-env} || :
kubectl delete job kubedt-pytest-{master,worker} || :
kubectl delete pod kubedt-pytest-master || :

sleep 5

pipenv run python submit.py --bucket foo --object-key bar \
  --access-key $ACCESS_KEY \
  --secret-key $SECRET_KEY \
  --namespace default \
  --s3-endpoint minio-minio-svc.default.svc.cluster.local:9000 \
  --inherit-envs OAUTH2_CLIENT_ID \
  OAUTH2_CLIENT_SECRET \
  OAUTH2_AUTHZ_ENDPOINT_URL \
  OAUTH2_TOKEN_ENDPOINT_URL \
  OAUTH2_SCOPES \
  HTTP_REQUEST_METHOD \
  HTTP_REQUEST_URL
