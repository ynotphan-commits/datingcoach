FROM python:3.12-slim

WORKDIR /app

# Install deps first (better layer caching)
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# App code
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY shared/ ./shared/

EXPOSE 8000

# Railway/Render inject $PORT; default to 8000 locally
CMD uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}
