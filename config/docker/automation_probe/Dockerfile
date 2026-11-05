# Build with --build-arg BROWSER_IMAGE=<local tag verified against runtime image ID>.
ARG BROWSER_IMAGE
FROM ${BROWSER_IMAGE}
USER root
ADD --checksum=sha256:463eb3cd6883ddd5c6721624b31f84f75d14f1a8930471a85c4b8b32ccc760cb \
    https://deb.debian.org/debian/pool/main/x/xautomation/xautomation_1.09-4_arm64.deb /tmp/xautomation.deb
RUN dpkg -i /tmp/xautomation.deb && rm /tmp/xautomation.deb
COPY scripts/gate-requirements.txt /tmp/probe-requirements.txt
RUN pip install --no-cache-dir -r /tmp/probe-requirements.txt
WORKDIR /repo
ENTRYPOINT []
