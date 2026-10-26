# Production image based on verified cbrowser foundation
FROM cbrowser:latest

WORKDIR /app

# Update backend source code
COPY src/backend/ /app/backend/
COPY src/backend/ /app/src/backend/

# Update built frontend assets
COPY src/frontend/dist/ /app/frontend/dist/

# Entrypoint script
COPY config/docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
