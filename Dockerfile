FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 10001 app
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /data/media /app/staticfiles && chown -R app:app /data /app/staticfiles
USER app
EXPOSE 8000
CMD ["sh", "deploy/entrypoint.sh"]
