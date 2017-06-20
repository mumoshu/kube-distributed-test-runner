FROM gcr.io/google-containers/ubuntu-slim:0.8
MAINTAINER Yusuke Kuoka "ykuoka@gmail.com"

RUN apt-get update && apt-get install --yes ca-certificates jq \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

# Add the wrapped resource S3
ADD ./rootfs /

# Add smuggler binary
RUN ln /opt/resource/smuggler /opt/resource/check && \
    ln /opt/resource/smuggler /opt/resource/in && \
    ln /opt/resource/smuggler /opt/resource/out

# Add the config file for this resource
ADD ./smuggler.yml /opt/resource/
