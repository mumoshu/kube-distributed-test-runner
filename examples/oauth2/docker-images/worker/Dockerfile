FROM mumoshu/kubedt-pytest-base:latest
MAINTAINER Yusuke Kuoka "ykuoka@gmail.com"

ADD . /kubedt/worker

WORKDIR /kubedt/worker

RUN pipenv install

ENTRYPOINT ["pipenv", "run", "python", "socketserver.py", ":8888"]
