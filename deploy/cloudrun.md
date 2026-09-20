# 1번 대시보드를 Cloud Run 에 올리기

maim 이 이미 같은 길을 갔습니다. **maim 이 데인 곳을 미리 피한 순서**입니다.

---

## 0. 미리 정할 것 두 가지

| | 무엇 | 비고 |
|---|---|---|
| 버킷 | maim 것을 같이 쓸지, 새로 만들지 | 같이 써도 `GCS_PREFIX=cash-flow` 로 갈라집니다 |
| 지역 | maim 과 같은 곳 | `gcloud run services list` 로 확인 |

```bash
# 지금 있는 서비스와 버킷 보기
gcloud run services list
gcloud storage buckets list
```

---

## 1. 버킷 (새로 만드실 때만)

```bash
gcloud storage buckets create gs://cashflow-state --location=us-central1
```

maim 버킷을 같이 쓰실 거면 이 단계는 건너뜁니다.

---

## 2. 접속 코드와 잠금 열쇠를 Secret 으로

**명령줄에 직접 적지 마십시오.** 셸 기록에 남습니다.

```bash
printf '바꾸실_접속코드' | gcloud secrets create dashboard-access-code --data-file=-
```

---

## 3. 배포

```bash
gcloud run deploy cash-flow \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --min-instances 0 \
  --memory 512Mi \
  --set-env-vars GCS_BUCKET=cashflow-state,GCS_PREFIX=cash-flow \
  --set-secrets DASHBOARD_ACCESS_CODE=dashboard-access-code:latest
```

### 왜 이 값들인가

| 설정 | 이유 |
|---|---|
| `--min-instances 0` | **안 쓸 때 잠듭니다. 요금이 여기서 갈립니다.** 1 이상이면 월 7달러 안팎이 계속 나갑니다 |
| `--allow-unauthenticated` | 구글 로그인 대신 **우리 접속 코드**로 막습니다. 고객이 구글 계정을 만들 필요가 없습니다 |
| `--memory 512Mi` | 화면을 그리는 일뿐이라 넉넉합니다 |
| `GCS_BUCKET` | 이게 없으면 **꺼질 때마다 고객 DB 가 날아갑니다** |
| `--set-secrets` | 접속 코드가 콘솔 화면에 평문으로 안 보이게 |

`PORT` 는 Cloud Run 이 알아서 줍니다. `Dockerfile` 이 그 값을 씁니다.

---

## 4. 확인

```bash
URL=$(gcloud run services describe cash-flow --region us-central1 --format='value(status.url)')
curl -sS "$URL/healthz"          # ok 가 나와야 합니다
echo "$URL"                       # 이 주소로 들어가십니다
```

---

## 5. maim 이 데인 곳 — 미리 피했습니다

| maim 이 겪은 것 | 여기서는 |
|---|---|
| **시작할 때 버킷 전체를 받다가 시작 제한 초과 → 배포 실패** | `core/gcsstate.py` 가 **DB 와 서명값 둘만** 받습니다. 산출물은 안 받습니다 |
| **GCS FUSE 마운트 위 SQLite 불안정** | 마운트하지 않습니다. 로컬 디스크에서 돌리고 60초마다 올립니다 |
| 토큰 게이트가 정적 파일까지 막음 | `/static` 과 `/healthz` 는 접속 코드에서 빠져 있습니다 (`OPEN_PATHS`) |
| 환경변수가 `YOUR_...` 자리표시자로 남음 | 그런 값은 **안 켠 것으로 봅니다**. 고장나지 않고 로컬 파일만 씁니다 |
| 요청 제한 5분에 걸림 | 연결 확인이 15초라 기본값으로 충분합니다 |

---

## 6. 요금 — 무엇이 돈이 되나

| 항목 | 언제 |
|---|---|
| **최소 인스턴스 ≥ 1** | 안 잠들게 둘 때. **여기가 제일 큽니다** |
| Cloud SQL | 안 씁니다 (SQLite + GCS) |
| Cloud Storage | 5GB 무료. DB 하나라 넘길 일이 없습니다 |
| 요청 수 | 월 200만 건 무료. 혼자 쓰시면 월 1만 건 남짓 — **1% 도 안 씁니다** |

혼자 쓰시는 한 **추가 청구가 사실상 없습니다.**

---

## 7. 고칠 것이 생기면

```bash
gcloud run deploy cash-flow --source . --region us-central1
```

환경변수는 그대로 남습니다. 다시 적을 필요가 없습니다.

---

## 8. 내리기

```bash
gcloud run services delete cash-flow --region us-central1
```

버킷은 남습니다. 지우시려면 `gcloud storage rm -r gs://cashflow-state`.
