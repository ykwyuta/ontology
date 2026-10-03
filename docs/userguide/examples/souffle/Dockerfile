# Soufflé（Datalog の処理系）2.5。公式リリースの Ubuntu 24.04 向けパッケージを使う
FROM ubuntu:24.04
ARG SOUFFLE_VERSION=2.5
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl \
 && curl -fsSL -o /tmp/souffle.deb \
      https://github.com/souffle-lang/souffle/releases/download/${SOUFFLE_VERSION}/x86_64-ubuntu-2404-souffle-${SOUFFLE_VERSION}-Linux.deb \
 && apt-get install -y --no-install-recommends /tmp/souffle.deb \
 && rm -rf /tmp/souffle.deb /var/lib/apt/lists/*
ENV LANG=C.UTF-8
