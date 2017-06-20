FROM mumoshu/kubedt-pytest-base:latest
MAINTAINER Yusuke Kuoka "ykuoka@gmail.com"

ADD . /kubedt/master

WORKDIR /kubedt/master

RUN pipenv install

ENTRYPOINT ["pipenv", "run", "python", "master.py"]
