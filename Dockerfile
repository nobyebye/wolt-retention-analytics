FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY requirements-lock.txt ./
COPY src ./src
RUN pip install --no-cache-dir -r requirements-lock.txt && pip install --no-cache-dir --no-deps .
COPY sql ./sql
COPY dashboard ./dashboard
COPY tests ./tests
RUN mkdir -p data/raw artifacts
CMD ["wolt-analytics", "--help"]
