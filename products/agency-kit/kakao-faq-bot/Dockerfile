# 카카오 FAQ 챗봇 — 고객 서버에 올리는 이미지
#
# 만들기:  docker build -t kakao-faq-bot .
# 띄우기:  docker compose up -d
#
# 오픈빌더는 **https 주소**만 받습니다. 이 컨테이너는 http 로 뜨므로
# 앞에 Caddy·Nginx 를 두거나 클라우드의 https 주소를 쓰세요.
# 설치 가이드 3장에 두 가지 길을 적어 두었습니다.

FROM python:3.11-slim

WORKDIR /app

# 먼저 의존성만 깔면, 코드가 바뀌어도 이 층은 다시 안 만듭니다(빌드가 빨라집니다).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 기록 파일과 서비스 계정 키는 볼륨으로 붙입니다. 이미지에 넣지 않습니다.
ENV LOG_DB_PATH=/data/logs.db \
    PORT=8080 \
    PYTHONUNBUFFERED=1
VOLUME ["/data"]

EXPOSE 8080

# 살아 있는지 봅니다. 시트를 못 읽으면 degraded 로 나오지만 서버는 살아 있습니다.
HEALTHCHECK --interval=60s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=4).status==200 else 1)"

CMD ["uvicorn", "app:get_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
