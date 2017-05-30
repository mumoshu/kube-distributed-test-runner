.PHONY: console
console:
	open $$(minikube service selenium-hub --url)/grid/console

add-node:
	kubectl run selenium-node-chrome --image selenium/node-chrome:2.53.1 --env="HUB_PORT_4444_TCP_ADDR=selenium-hub" --env="HUB_PORT_4444_TCP_PORT=4444"

python:
	kubectl run selenium-python --image=google/python-hello

build:
	hack/containerized-build

docker-build: build
	docker build -t mumoshu/kube-selenium .

web-kube-run: docker-build
	if kubectl get deployment kube-selenium 2>&1 > /dev/null; then kubectl delete deployment kube-selenium; fi
	kubectl run kube-selenium -i --env=REDIS_HOST=kube-selenium-redis-redis:6379 --env=REDIS_PASSWORD=$$(hack/ctl redis_password) --env=MYSQL_HOST=kube-selenium-mysql-mysql --env=MYSQL_USER=root --env=MYSQL_PASSWORD=$$(hack/ctl mysql_password) --image=mumoshu/kube-selenium:latest --image-pull-policy=IfNotPresent

deps-kube-run:
	if ! helm list | grep kube-selenium-mysql; then helm install --name kube-selenium-mysql --set mysqlDatabase=kube_selenium stable/mysql; fi
	if ! helm list | grep kube-selenium-redis; then helm install --name kube-selenium-redis stable/redis; fi

format:
	test -z "$$(find . -path ./vendor -prune -type f -o -name '*.go' -exec gofmt -d {} + | tee /dev/stderr)" || \
	test -z "$$(find . -path ./vendor -prune -type f -o -name '*.go' -exec gofmt -w {} + | tee /dev/stderr)"
