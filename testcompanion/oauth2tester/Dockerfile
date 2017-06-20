FROM gcr.io/google-containers/ubuntu-slim:0.8
MAINTAINER Yusuke Kuoka "ykuoka@gmail.com"

RUN apt-get update && apt-get install --yes ca-certificates \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

ADD linux-amd64/kube-selenium kube-selenium
ADD views views

CMD ./kube-selenium

EXPOSE 8000 80
