FROM ubuntu:24.04

ARG TARGETARCH

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl unzip bash git python3 \
    && rm -rf /var/lib/apt/lists/*

RUN set -eu; \
    test "${TARGETARCH}" = "amd64"; \
    test "$(/usr/bin/dpkg --print-architecture)" = "amd64"; \
    archive_sha256="194fe81e24ae7cc1f3141fd1d42db6cb60f03d42735d12ae865fe2db11ea6f0e"; \
    binary_sha256="3b13b10838fb7f7aafae16a9a01085439c75619bb9b78a1b5b787eab81ddf6e4"; \
    install_root="/tmp/aftman-install"; \
    archive_path="${install_root}/aftman.zip"; \
    extracted_path="${install_root}/extracted/aftman"; \
    /bin/rm -rf "${install_root}"; \
    /bin/mkdir -p "${install_root}/extracted"; \
    /usr/bin/curl --disable --fail --silent --show-error --location \
        https://github.com/LPGhatguy/aftman/releases/download/v0.3.0/aftman-0.3.0-linux-x86_64.zip \
        -o "${archive_path}"; \
    /usr/bin/printf '%s  %s\n' "${archive_sha256}" "${archive_path}" \
        | /usr/bin/sha256sum --check --strict -; \
    /usr/bin/unzip -j "${archive_path}" -d "${install_root}/extracted"; \
    test -f "${extracted_path}"; \
    test ! -L "${extracted_path}"; \
    /usr/bin/printf '%s  %s\n' "${binary_sha256}" "${extracted_path}" \
        | /usr/bin/sha256sum --check --strict -; \
    /usr/bin/install -m 0755 "${extracted_path}" /usr/local/bin/aftman; \
    test -f /usr/local/bin/aftman; \
    test ! -L /usr/local/bin/aftman; \
    /usr/bin/printf '%s  %s\n' "${binary_sha256}" /usr/local/bin/aftman \
        | /usr/bin/sha256sum --check --strict -; \
    /bin/rm -rf "${install_root}"

COPY --chmod=755 scripts/docker-entrypoint.sh /usr/local/bin/racer-docker-entrypoint

RUN /usr/sbin/groupadd --gid 1000 codex \
    && /usr/sbin/useradd \
        --uid 1000 \
        --gid codex \
        --create-home \
        --shell /bin/bash \
        codex \
    && /usr/bin/install -d -m 0755 -o codex -g codex /home/codex/.aftman

ENV HOME="/home/codex"
USER codex
WORKDIR /workspace

ENV PATH="/home/codex/.aftman/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

ENTRYPOINT ["/usr/local/bin/racer-docker-entrypoint"]
CMD ["bash"]
