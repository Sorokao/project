FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY seed.py .
COPY static ./static
ENV DATABASE_URL=sqlite:////data/vdrama.db
VOLUME /data
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
