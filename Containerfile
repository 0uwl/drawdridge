FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN useradd --uid 1000 --create-home appuser

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chown -R appuser:appuser /app

USER appuser

ENV FLASK_ENV=production

EXPOSE 8080

# /app/data and /app/scripts are mount points (see docs/drawbridge.md) — do
# not bake content into the image; bind-mount them at runtime.
CMD ["gunicorn", "drawbridge:create_app()"]
