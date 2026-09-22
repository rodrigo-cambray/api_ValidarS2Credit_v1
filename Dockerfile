FROM python:3.12-slim
WORKDIR /app
ENV VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app \
    PYTHONNOUSERSITE=1
COPY requirements.txt .
RUN python -m venv $VIRTUAL_ENV && \
    $VIRTUAL_ENV/bin/pip install --no-cache-dir -r requirements.txt
COPY app ./app
RUN useradd --create-home appuser
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
