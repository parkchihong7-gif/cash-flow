#!/usr/bin/env bash
#
# 1번 대시보드를 Cloud Run 에 올립니다.
#
#   구글 클라우드 콘솔 → 위쪽 [>_] (Cloud Shell) → 이 줄을 붙여 넣으세요
#
#       git clone https://github.com/parkchihong7-gif/cash-flow
#       cd cash-flow && bash deploy/올리기.sh
#
# bash 는 변수 이름에 한글을 못 씁니다(파이썬·자바스크립트와 다릅니다).
# 그래서 이름만 영문이고 설명은 한글입니다.
#
# 물어보는 것은 접속 코드 하나뿐입니다. 나머지는 알아서 찾습니다.
# 여러 번 돌려도 됩니다 — 이미 만든 것은 그냥 넘어갑니다.

set -euo pipefail

SERVICE=cash-flow
PREFIX=cash-flow          # 한 버킷을 maim 과 같이 써도 섞이지 않게 하는 이름
SECRET=dashboard-access-code

echo
echo "════════════════════════════════════════════════════"
echo "  통합 관리자 대시보드 — Cloud Run 에 올리기"
echo "════════════════════════════════════════════════════"
echo

# ── 1. 프로젝트 확인 ────────────────────────────────────
PROJECT=$(gcloud config get-value project 2>/dev/null || true)
if [ -z "$PROJECT" ] || [ "$PROJECT" = "(unset)" ]; then
  echo "✗ 프로젝트가 정해져 있지 않습니다."
  echo "  gcloud projects list 로 이름을 보시고"
  echo "  gcloud config set project <이름> 을 먼저 하세요."
  exit 1
fi
echo "프로젝트 : $PROJECT"

# ── 2. 지역 찾기 ────────────────────────────────────────
#
# 같은 지역끼리는 통신이 빠르고 공짜다. 이미 돌고 있는 서비스가 있으면
# **그 옆에** 두는 것이 맞다. 없으면 미국 아이오와를 쓴다 (가장 싸고 흔한 곳).
REGION=$(gcloud run services list --format='value(REGION)' 2>/dev/null | head -1 || true)
if [ -z "$REGION" ]; then
  REGION=us-central1
  echo "지역     : $REGION  (돌고 있는 서비스가 없어 기본값)"
else
  echo "지역     : $REGION  (이미 돌고 있는 서비스와 같은 곳)"
fi

# ── 3. 버킷 ─────────────────────────────────────────────
#
# 컨테이너가 꺼지면 디스크가 비워진다. 고객 DB 와 발급한 키를 여기에 둔다.
# 버킷 이름은 **전 세계에서 겹치면 안 된다.** 그래서 프로젝트 이름을 붙인다.
BUCKET=$(gcloud storage buckets list --format='value(name)' 2>/dev/null \
        | grep -i -m1 -E 'maim|state|cash' || true)
if [ -n "$BUCKET" ]; then
  echo "버킷     : $BUCKET  (이미 있는 것을 씁니다 · 앞머리 $PREFIX 로 갈라집니다)"
else
  BUCKET="${PROJECT}-state"
  echo "버킷     : $BUCKET  (새로 만듭니다)"
  gcloud storage buckets create "gs://$BUCKET" --location="$REGION" \
    --uniform-bucket-level-access >/dev/null
  echo "           만들었습니다."
fi

# ── 4. 접속 코드 ────────────────────────────────────────
#
# 명령줄에 직접 적으면 셸 기록에 남는다. Secret Manager 에 넣는다.
if gcloud secrets describe "$SECRET" >/dev/null 2>&1; then
  echo "접속코드 : 이미 넣어 두신 것을 씁니다"
else
  # 이 기능을 켜는 데 30~60초 걸린다. 조용히 두면 멈춘 줄 안다.
  echo
  echo "비밀 보관 기능을 켜는 중입니다 (처음 한 번, 30초~1분)..."
  gcloud services enable secretmanager.googleapis.com >/dev/null 2>&1 || true
  echo "           켰습니다."
  echo
  echo "────────────────────────────────────────────────────"
  echo " 이 대시보드를 열 때 쓸 **접속 코드**를 정하세요."
  echo
  echo "  · 여섯 자 이상"
  echo "  · **치셔도 화면에 아무것도 안 보입니다** (비밀번호라서)"
  echo "    그냥 치고 Enter 를 누르세요"
  echo "  · 잊으면 다시 만들어야 하니 적어 두세요"
  echo "────────────────────────────────────────────────────"
  printf "  접속 코드: "
  read -rs CODE
  echo
  if [ ${#CODE} -lt 6 ]; then
    echo "✗ 너무 짧습니다. 여섯 자 이상으로 하세요."
    exit 1
  fi
  printf '%s' "$CODE" | gcloud secrets create "$SECRET" --data-file=- >/dev/null
  unset CODE
  echo "접속코드 : 넣었습니다"
fi

# ── 5. 올리기 ───────────────────────────────────────────
echo
echo "────────────────────────────────────────────────────"
echo " 올리는 중입니다. **처음에는 3~5분 걸립니다.**"
echo " 중간에 멈춘 것처럼 보여도 기다려 주세요."
echo "────────────────────────────────────────────────────"
echo

gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --min-instances 0 \
  --memory 512Mi \
  --set-env-vars "GCS_BUCKET=$BUCKET,GCS_PREFIX=$PREFIX" \
  --set-secrets "DASHBOARD_ACCESS_CODE=${SECRET}:latest" \
  --quiet

# ── 6. 확인 ─────────────────────────────────────────────
URL=$(gcloud run services describe "$SERVICE" --region "$REGION" \
        --format='value(status.url)')

echo
echo "════════════════════════════════════════════════════"
if curl -fsS --max-time 30 "$URL/healthz" >/dev/null 2>&1; then
  echo "  ✓ 올라갔고 살아 있습니다."
else
  echo "  △ 올라갔지만 아직 안 깨어났습니다 (처음엔 느립니다)."
fi
echo
echo "  $URL"
echo
echo "  이 주소를 여시고 방금 정하신 접속 코드를 넣으세요."
echo "════════════════════════════════════════════════════"
echo
echo "다음에 고칠 것이 생기면 이 줄 하나면 됩니다:"
echo "  gcloud run deploy $SERVICE --source . --region $REGION"
echo
echo "요금: 안 쓸 때는 잠들어서 붙지 않습니다 (--min-instances 0)."
echo "내리려면: gcloud run services delete $SERVICE --region $REGION"
echo
