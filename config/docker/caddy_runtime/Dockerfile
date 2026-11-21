FROM --platform=$BUILDPLATFORM python:3.15-slim-trixie@sha256:8c13a3f37a6a5b71498228e902c4b9f51c1f7900d49fabf71f9a650c6120e0d0 AS frontend
ARG BUILDARCH
ARG APT_MIRROR=mirrors.tuna.tsinghua.edu.cn
RUN sed -i "s|^URIs: http://deb.debian.org/|URIs: http://$APT_MIRROR/|" /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=3 -o APT::Update::Error-Mode=any update \
    && apt-get -o Acquire::Retries=3 install -y --no-install-recommends libatomic1 \
    && rm -rf /var/lib/apt/lists/*

# Use the pinned upstream Node distribution on the builder's architecture.
RUN python3 - <<'PYTHON'
import hashlib
import os
import tarfile
from pathlib import Path
from shutil import copyfileobj
from tempfile import TemporaryFile
from urllib.request import urlopen

arch, expected = {
    "arm64": ("arm64", "406fe3fbde1c054adff8b297c16fdb5af6659db327c1ac8acd46b56ef1af9a92"),
    "amd64": ("x64", "d28a96af6c38596f6d9d97c0ee531c13d238d757742387d1928de822d959e997"),
}[os.environ["BUILDARCH"]]
name = f"node-v26.13.0-linux-{arch}"
url = f"https://nodejs.org/dist/v26.13.0/{name}.tar.xz"
with TemporaryFile() as payload:
    with urlopen(url, timeout=60) as response:
        copyfileobj(response, payload)
    payload.seek(0)
    if hashlib.file_digest(payload, "sha256").hexdigest() != expected:
        raise RuntimeError("Node distribution SHA-256 mismatch")
    payload.seek(0)
    with tarfile.open(fileobj=payload, mode="r:xz") as bundle:
        bundle.extractall("/opt", filter="data")
Path("/opt", name).rename("/opt/node")
PYTHON
ENV PATH="/opt/node/bin:${PATH}"
WORKDIR /app/src/frontend
COPY src/frontend/package.json src/frontend/package-lock.json ./
RUN npm ci
COPY src/frontend ./
COPY scripts /app/scripts
COPY DESIGN.md /app/
COPY config/selkies/selkies_web_sha256.txt /app/config/selkies/
RUN npm run build

FROM caddy:2-alpine@sha256:70b3180738b46cd88e49b300d790ae448a0aca3f58edef0f000bb57d619a9ab3
COPY --from=frontend /app/src/frontend/dist /var/www/html
