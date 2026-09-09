# The Owner Intelligence service, packaged whole.
#
# The image carries the application AND the trusted evidence export, because the evidence IS the
# product: every figure the owner sees is reconstructed from these CSVs at startup, and a
# container that had to fetch them would be a container that can serve a different answer than
# the one that was validated. Bundling them keeps the deployed system byte-identical to the
# validated one, and keeps the service independent of any external store at read time.
#
# Nothing is compiled, generated or transformed at build time. No calculation, registry, gate
# rule or evidence file is touched here.

FROM python:3.13-slim

# Faster start, smaller image, and tracebacks that reach the platform's log stream unbuffered.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first, so a change to the application or the evidence does not reinstall them.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# The application and its evidence. .dockerignore keeps the tests, caches and working notes out.
COPY . .

# The evidence root. Derived from the package location by default; stated explicitly here so the
# image does not depend on where it happens to be unpacked.
ENV AI_ANALYTICS_BASE=/app

# The platform supplies PORT. Bind every interface -- a container that binds loopback is a
# container nothing can reach.
ENV AI_ANALYTICS_HOST=0.0.0.0
EXPOSE 8000

# Not `python serve.py`: that script is the local developer entry point and refuses to start
# without a local-development flag. Uvicorn is given the app factory directly, and the service
# builds its payloads during startup so the first request does not pay for the whole engine.
CMD ["sh", "-c", "uvicorn api.wsgi:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --timeout-keep-alive 65"]
