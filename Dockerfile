FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash openssh-server \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=5000

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./
COPY templates ./templates
COPY static ./static
COPY entrypoint.sh ./
COPY sshd_config /etc/ssh/sshd_config
RUN chmod 755 /app/entrypoint.sh

EXPOSE 5000 22

CMD ["/app/entrypoint.sh"]
