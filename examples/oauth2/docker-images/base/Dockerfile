FROM gcr.io/google-containers/ubuntu-slim:0.8
MAINTAINER Yusuke Kuoka "ykuoka@gmail.com"

RUN apt-get update && apt-get install --yes python python-pip ca-certificates \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip \
  && pip install pipenv
