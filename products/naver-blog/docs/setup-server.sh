(
set -e
S={{SERVER}}; R=us-central1
P=$(gcloud config get-value project 2>/dev/null)
[ -n "$P" ] || { echo "⚠ 구글 클라우드 프로젝트가 아직 없습니다 — 도우미 0단계(프로젝트·결제 계정)를 먼저 해 주세요."; false; }
echo "▶ 1/5 필요한 기능 켜기 (1~2분)"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com cloudscheduler.googleapis.com storage.googleapis.com
echo "▶ 2/5 저장통 만들기 (글이 쌓이는 곳)"
B=$S-data-$P
gcloud storage buckets describe gs://$B >/dev/null 2>&1 || gcloud storage buckets create gs://$B --location=$R
echo "▶ 3/5 프로그램 받기"
if [ -d ~/maim ]; then git -C ~/maim pull -q; else git clone -q https://github.com/parkchihong7-gif/maim.git ~/maim; fi
cd ~/maim
if gcloud run services describe $S --region=$R >/dev/null 2>&1; then
  echo "▶ 4/5 서버가 이미 있습니다 — 설정을 지키려고 다시 세우지 않습니다"
else
  [ -s ~/$S-비밀번호.txt ] || openssl rand -hex 6 > ~/$S-비밀번호.txt
  PW=$(cat ~/$S-비밀번호.txt)
  echo "▶ 4/5 서버 세우기 (5~10분 — 이 창을 닫지 마세요)"
  gcloud run deploy $S --source . --region=$R --allow-unauthenticated --quiet \
    --memory=2Gi --min-instances=0 --max-instances=1 --concurrency=80 --timeout=1800 \
    --set-env-vars=HOST=0.0.0.0,DATA_DIR=/tmp/maim-state,HOME=/tmp/maim-state/home,GCS_STATE_BUCKET=$B,TIMEZONE=Asia/Seoul,CLAUDE_BIN=claude,DASHBOARD_TOKEN=$PW,KEYSERVER_URL={{KEYSERVER_URL}},KEYSERVER_PROGRAM={{PROGRAM}}
fi
URL=$(gcloud run services describe $S --region=$R --format='value(status.url)')
PW=$(cat ~/$S-비밀번호.txt 2>/dev/null || true)
echo "▶ 5/5 아침 6시 자동 준비 걸기"
gcloud scheduler jobs describe $S-daily --location=$R >/dev/null 2>&1 || gcloud scheduler jobs create http $S-daily --location=$R --schedule="0 6 * * *" --time-zone="Asia/Seoul" --uri="$URL/api/run/daily" --http-method=POST --attempt-deadline=1800s --headers="x-dashboard-token=$PW"
echo ""
echo "🎉 완료! 사장님 접속 주소 → $URL"
echo "   관리용 비밀번호 → $PW   (검은 창의 ~/$S-비밀번호.txt 에도 저장해 두었습니다)"
)
