test:
	echo '{"foo":1,"source":{"configmap":"foobar", "path":"/app"}}' | kubectl run test --rm --restart=Never -i --image mumoshu/concourse-kube-broker-resource --quiet -- /opt/resource/check

test-up:
	kubectl run test -it --image mumoshu/concourse-kube-broker-resource -- bash

test-down:
	kubectl delete deployment test

test-run: CA_PATH = $(shell kubectl config view -o json | jq -r '.clusters[] | select(.name == "minikube") | .cluster["certificate-authority"]')
test-run: CA_BASE64 = $(shell cat $(CA_PATH) | base64)
test-run: TOKEN_BASE64 = $(shell kubectl get secret default-token-9w5xg -o jsonpath={.data.token})
test-run:
	echo '{"foo":1,"source":{"configmap":"foobar", "path":"/app", "k8s_ca":"$(CA_BASE64)", "k8s_service_account_token":"$(TOKEN_BASE64)"}}' | kubectl exec -it $$(kubectl get po --selector run=test -o=jsonpath={.items[].metadata.name}) -- /opt/resource/check

test-attach:
	kubectl attach $$(kubectl get po --selector run=test -o=jsonpath={.items[].metadata.name}) -c test -i -t

build:
	./build.sh
