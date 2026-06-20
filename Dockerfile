# ---------------------------------------------------------------------------
# Cority ESBD Opportunity Engine — container image for Render (or any Docker host)
# ---------------------------------------------------------------------------
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PIP_NO_CACHE_DIR=1 \
    # Put the Chromium binary in a stable, world-readable location.
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# 1) Python deps, then the Chromium browser + its system libraries.
#    Installing the browser via the matching playwright version avoids drift.
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --upgrade pip \
 && pip install -r backend/requirements.txt \
 && playwright install --with-deps chromium

# 2) Application code (data/ is created at runtime / mounted as a disk).
COPY backend ./backend
COPY frontend ./frontend
COPY assets ./assets

WORKDIR /app/backend

EXPOSE 5000

# Single gunicorn worker (the in-memory job registry must be shared), several
# threads for the poll endpoints. Long timeout because agent subprocesses run
# independently but the worker should never be recycled mid-poll.
CMD gunicorn --workers 1 --threads 8 --timeout 180 --pythonpath . \
    --bind 0.0.0.0:${PORT:-5000} app:app
