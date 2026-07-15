FROM ubuntu:24.04

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl unzip bash git python3 \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://github.com/LPGhatguy/aftman/releases/download/v0.3.0/aftman-0.3.0-linux-x86_64.zip -o /tmp/aftman.zip \
    && unzip -j /tmp/aftman.zip -d /usr/local/bin \
    && chmod +x /usr/local/bin/aftman \
    && rm /tmp/aftman.zip

COPY --chmod=755 scripts/docker-entrypoint.sh /usr/local/bin/racer-docker-entrypoint

RUN useradd -m -s /bin/bash codex
USER codex
WORKDIR /workspace

ENV PATH="/home/codex/.aftman/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

ENTRYPOINT ["/usr/local/bin/racer-docker-entrypoint"]
CMD ["bash"]
