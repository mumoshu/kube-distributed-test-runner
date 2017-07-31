build:
	hack/containerized-build

docker-build: build
	docker build -t mumoshu/oauth2clientweb .

kube-svc: docker-build kube-deps
	if kubectl get deployment kube-selenium 2>&1 > /dev/null; then kubectl delete deployment kube-selenium; fi
	kubectl run kube-selenium -i --env=REDIS_HOST=kube-selenium-redis-redis:6379 --env=REDIS_PASSWORD=$$(../../hack/ctl redis_password) --env=MYSQL_HOST=kube-selenium-mysql-mysql --env=MYSQL_USER=root --env=MYSQL_PASSWORD=$$(../../hack/ctl mysql_password) --image=mumoshu/oauth2clientweb:latest --image-pull-policy=IfNotPresent
	if kubectl get service kube-selenium 2>&1 > /dev/null; then kubectl delete service kube-selenium; fi
	kubectl expose deployment kube-selenium --port 8000 --target-port 8000 --type NodePort

kube-deps:
	if ! helm list | grep ^selenium-grid; then helm install --set chromeDebug.enabled=true --set firefoxDebug.enabled=true --set hub.tag=2.53.1 --set chromeDebug.tag=2.53.1 --set firefoxDebug.tag=2.53.1 --name selenium-grid stable/selenium; fi
	if ! helm list | grep kube-selenium-mysql; then helm install --name kube-selenium-mysql --set mysqlDatabase=kube_selenium stable/mysql; fi
	if ! helm list | grep kube-selenium-redis; then helm install --name kube-selenium-redis stable/redis; fi

format:
	test -z "$$(find . -path ./vendor -prune -type f -o -name '*.go' -exec gofmt -d {} + | tee /dev/stderr)" || \
	test -z "$$(find . -path ./vendor -prune -type f -o -name '*.go' -exec gofmt -w {} + | tee /dev/stderr)"
