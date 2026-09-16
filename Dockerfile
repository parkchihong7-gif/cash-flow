# 통합 관리자 대시보드를 클라우드에 올릴 때 쓰는 설정입니다.
# Render·Railway·Fly 같은 곳이 이 파일을 읽어 그대로 만들어 줍니다.

FROM python:3.11-slim

# 한글이 깨지지 않게, 그리고 로그가 바로 보이게
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LANG=C.UTF-8

WORKDIR /app

# 먼저 목록만 복사해 설치한다. 코드만 고쳤을 때 설치를 다시 하지 않게 하려는 것.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 고객 DB 와 세션 서명값을 여기에 둔다. 호스팅에서 이 경로에 디스크를 붙여야
# 다시 배포해도 고객 정보가 남는다. 안 붙이면 배포할 때마다 지워진다.
#
# 산출물(엑셀·리포트 등)은 여기 들어오지 않아서 배포 때 사라진다.
# 다시 만들면 되는 것들이라 그대로 두었다.
ENV DASHBOARD_DATA_DIR=/app/data
RUN mkdir -p /app/data
VOLUME ["/app/data"]

# 호스팅이 PORT 를 정해 주면 그 값을 쓴다. 없으면 8000.
ENV PORT=8000
EXPOSE 8000

# 살아 있는지 확인하는 주소. 접속 코드 없이 열리는 유일한 곳이다.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\",\"8000\")}/healthz')"

CMD ["python", "-m", "dashboard"]
