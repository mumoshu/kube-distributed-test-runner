FROM gcr.io/google-containers/ubuntu-slim:0.8
MAINTAINER Yusuke Kuoka "ykuoka@gmail.com"

RUN apt-get update && apt-get install --yes ca-certificates \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

ADD linux-amd64/oauth2clientweb oauth2clientweb
ADD views views

ENTRYPOINT ["/oauth2clientweb"]

EXPOSE 8000 80
