# Image chạy API ở production (AWS ECS/EC2). Local dev không cần image này: dùng `uv run fastapi dev`.
#   docker build -t thiepcuoi-api .
#   docker run --env-file .env -p 8000:8000 thiepcuoi-api
#   docker run --env-file .env thiepcuoi-api alembic upgrade head
#   docker run --env-file .env thiepcuoi-api python -m app.scripts.seed_templates
FROM python:3.13-slim

# uv cùng phiên bản đọc được uv.lock (revision 5)
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Cài thư viện trước để layer này được cache khi chỉ sửa code.
# --locked: uv.lock lệch với pyproject.toml thì build lỗi thay vì tự resolve lại
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

ENV PATH="/app/.venv/bin:$PATH"

RUN useradd --create-home --uid 10001 app
USER app

EXPOSE 8000

# Chạy sau load balancer (ALB): tin header X-Forwarded-* để biết request gốc là https
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
