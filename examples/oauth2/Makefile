.PHONY: docker-images
docker-images:
	rm -Rf build/base && mkdir -p build/base && cp Pipfile docker-images/base/* build/base/ && cd build/base && docker build -t mumoshu/kubedt-pytest-base:latest .
	rm -Rf build/master && mkdir -p build/master && cp Pipfile docker-images/master/* build/master && cd build/master && docker build -t mumoshu/kubedt-pytest-master:latest .
	rm -Rf build/worker && mkdir -p build/worker && cp Pipfile docker-images/worker/* build/worker && cd build/worker && docker build -t mumoshu/kubedt-pytest-worker:latest .
