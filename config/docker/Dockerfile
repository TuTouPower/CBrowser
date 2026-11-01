# Production image based on verified cbrowser foundation
FROM cbrowser:latest

WORKDIR /app

# Update backend source code
COPY src/backend/ /app/backend/
COPY src/backend/ /app/src/backend/

# Update built frontend assets
COPY src/frontend/dist/ /app/frontend/dist/

# Fail the image build if the prebuilt dist lacks vendored Selkies assets,
# the hash manifest does not match, or the classic adapter is missing.
COPY scripts/vendor_selkies_web.py /app/scripts/vendor_selkies_web.py
COPY scripts/verify_frontend_dist.py /app/scripts/verify_frontend_dist.py
COPY config/selkies/selkies_web_sha256.txt /app/config/selkies/selkies_web_sha256.txt
RUN python3 /app/scripts/verify_frontend_dist.py \
    --dist /app/frontend/dist \
    --manifest /app/config/selkies/selkies_web_sha256.txt

# Entrypoint script
COPY config/docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
