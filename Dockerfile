FROM python:3.12-slim

WORKDIR /app

# Install only the runtime dependencies for the multiplayer server.
RUN pip install --no-cache-dir \
    "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.30.0" \
    "pydantic>=2.0"

COPY server ./server
COPY static ./static

EXPOSE 8000

CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
