(
set -e
S={{SERVER}}; R=us-central1
P=$(gcloud config get-value project 2>/dev/null || true)
if [ -z "$P" ]; then
  # 검은 창에 프로젝트가 안 정해져 있으면: 하나뿐이면 그것을, 없으면 새로 만든다. 여럿이면 고르게 한다.
  N=$(gcloud projects list --format='value(projectId)' 2>/dev/null | grep -c . || true)
  if [ "$N" = 1 ]; then
    P=$(gcloud projects list --format='value(projectId)'); echo "▶ 0/5 프로젝트 $P 를 씁니다"
  elif [ "$N" = 0 ]; then
    P=$S-$(openssl rand -hex 2); echo "▶ 0/5 프로젝트 $P 만들기"
    gcloud projects create $P --name="blog-posting"
  else
    echo "⚠ 프로젝트가 여러 개입니다. 쓸 것의 ID 를 골라 아래 한 줄을 친 뒤 다시 붙여넣으세요:"
    gcloud projects list --format='table(projectId,name)'
    echo "   gcloud config set project 고른-프로젝트-ID"; false
  fi
  gcloud config set project $P
fi
if [ "$(gcloud billing projects describe $P --format='value(billingEnabled)' 2>/dev/null)" != "True" ]; then
  # 서버를 세우려면 결제 계정이 연결돼 있어야 한다(무료 한도 안이라 거의 0원). 있으면 이어 주고, 없으면 만들 곳을 알려 준다.
  BA=$(gcloud billing accounts list --filter=open=true --format='value(name)' --limit=1 2>/dev/null)
  if [ -n "$BA" ]; then
    echo "▶ 0/5 결제 계정 연결"; gcloud billing projects link $P --billing-account=${BA##*/}
  else
    echo ""
    echo "⚠ 이 구글 계정에 결제 계정이 없어 여기서 멈췄습니다 (서버는 아직 안 만들어졌습니다)."
    echo "   ① 아래 주소를 열어 [무료로 시작하기] → 카드 등록 (무료 한도 안이라 거의 0원, 자동 결제 안 됨)"
    echo "      https://console.cloud.google.com/freetrial"
    echo "   ② 끝나면 이 명령을 **그대로 다시 붙여넣기** — 결제 계정 연결부터 이어서 합니다 (프로젝트: $P)"; false
  fi
fi
echo "▶ 1/5 필요한 기능 켜기 (1~2분)"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com cloudscheduler.googleapis.com storage.googleapis.com
echo "▶ 2/5 저장통 만들기 (글이 쌓이는 곳)"
B=$S-data-$P
gcloud storage buckets describe gs://$B >/dev/null 2>&1 || gcloud storage buckets create gs://$B --location=$R
# 새 프로젝트의 기본 서비스 계정은 권한이 비어 있어 빌드·저장통 읽기가 막힌다(PERMISSION_DENIED). 필요한 만큼만 준다.
SA=$(gcloud projects describe $P --format='value(projectNumber)')-compute@developer.gserviceaccount.com
gcloud projects add-iam-policy-binding $P --member=serviceAccount:$SA --role=roles/run.builder --condition=None --quiet >/dev/null
gcloud storage buckets add-iam-policy-binding gs://$B --member=serviceAccount:$SA --role=roles/storage.objectAdmin >/dev/null
echo "▶ 3/5 프로그램 받기"
if [ -d ~/maim ]; then git -C ~/maim pull -q; else git clone -q https://github.com/parkchihong7-gif/maim.git ~/maim; fi
cd ~/maim
if gcloud run services describe $S --region=$R >/dev/null 2>&1; then
  echo "▶ 4/5 서버가 이미 있습니다 — 설정을 지키려고 다시 세우지 않습니다"
else
  [ -s ~/$S-비밀번호.txt ] || openssl rand -hex 6 > ~/$S-비밀번호.txt
  PW=$(cat ~/$S-비밀번호.txt)
  echo "▶ 4/5 서버 세우기 (5~10분 — 이 창을 닫지 마세요)"
  deploy_it() { gcloud run deploy $S --source . --region=$R --allow-unauthenticated --quiet \
    --memory=2Gi --min-instances=0 --max-instances=1 --concurrency=80 --timeout=1800 \
    --set-env-vars=HOST=0.0.0.0,DATA_DIR=/tmp/maim-state,HOME=/tmp/maim-state/home,GCS_STATE_BUCKET=$B,TIMEZONE=Asia/Seoul,CLAUDE_BIN=claude,DASHBOARD_TOKEN=$PW,KEYSERVER_URL={{KEYSERVER_URL}},KEYSERVER_PROGRAM={{PROGRAM}}; }
  # 방금 준 권한은 퍼지는 데 1~2분 걸릴 수 있다 — 처음 실패하면 한 번만 기다렸다 다시 세운다.
  deploy_it || { echo "   (권한이 퍼지는 중 — 1분 기다렸다 한 번 더 세웁니다)"; sleep 60; deploy_it; }
fi
URL=$(gcloud run services describe $S --region=$R --format='value(status.url)')
PW=$(cat ~/$S-비밀번호.txt 2>/dev/null || true)
echo "▶ 5/5 아침 6시 자동 준비 걸기"
gcloud scheduler jobs describe $S-daily --location=$R >/dev/null 2>&1 || gcloud scheduler jobs create http $S-daily --location=$R --schedule="0 6 * * *" --time-zone="Asia/Seoul" --uri="$URL/api/run/daily" --http-method=POST --attempt-deadline=1800s --headers="x-dashboard-token=$PW"
echo ""
echo "🎉 완료! 사장님 접속 주소 → $URL"
echo "   관리용 비밀번호 → $PW   (검은 창의 ~/$S-비밀번호.txt 에도 저장해 두었습니다)"
)
