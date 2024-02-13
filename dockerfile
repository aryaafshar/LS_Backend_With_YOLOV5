FROM python:3.8

WORKDIR /tmp
COPY requirements.txt .

ENV PYTHONUNBUFFERED=True \
    PORT=${PORT:-9090} \
    PIP_CACHE_DIR=/.cache

RUN --mount=type=cache,target=$PIP_CACHE_DIR \
    pip install -r requirements.txt


COPY uwsgi.ini /etc/uwsgi/
COPY supervisord.conf /etc/supervisor/conf.d/

WORKDIR /app

RUN curl -O https://github.com/ultralytics/assets/releases/download/v8.1.0/yolov8n.pt
COPY * /app/
COPY /_base_/ /app/_base_/


EXPOSE 9090

ENV checkpoint_file=yolov8n.pt


CMD ["/usr/local/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
