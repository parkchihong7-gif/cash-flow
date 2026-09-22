# 1번 대시보드를 Cloud Run 에 올리기

## 한 줄로 끝내기 (이게 제일 쉽습니다)

구글 클라우드 콘솔 → 위쪽 **[>_]** 단추(Cloud Shell) → 아래를 붙여 넣으세요.

```bash
git clone https://github.com/parkchihong7-gif/cash-flow
cd cash-flow && bash deploy/올리기.sh
```

**물어보는 것은 접속 코드 하나뿐입니다.** 지역·버킷은 알아서 찾습니다.
여러 번 돌리셔도 됩니다 — 이미 만든 것은 그냥 넘어갑니다.

끝나면 주소가 나옵니다. 그 주소를 열고 정하신 접속 코드를 넣으시면 됩니다.

---

## 스크립트가 알아서 하는 것

| | 어떻게 정하나 |
|---|---|
| **지역** | 이미 돌고 있는 서비스와 **같은 곳**. 없으면 `us-central1` |
| **버킷** | 이미 있는 것(maim 것 포함)을 찾아 씁니다. 없으면 `<프로젝트>-state` 로 새로 |
| **접속 코드** | 한 번 물어보고 Secret Manager 에 넣습니다 (셸 기록에 안 남게) |

> **지역이 뭔가요**
> 구글 서버가 물리적으로 어느 도시에 있는지입니다. `us-central1` 은 미국
> 아이오와, `asia-northeast3` 은 서울. **같은 지역끼리는 통신이 빠르고 공짜**라
> maim 옆에 두는 것이 낫습니다.

> **버킷을 maim 과 같이 써도 되나요**
> 됩니다. `GCS_PREFIX=cash-flow` 로 폴더가 갈라져 섞이지 않습니다.
> 버킷 이름은 **전 세계에서 겹치면 안 되므로**, 새로 만들 때는 프로젝트
> 이름을 앞에 붙입니다.

---

## 손으로 하실 때

아래는 스크립트가 하는 일을 한 줄씩 푼 것입니다. 뭔가 어긋났을 때 보세요.

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

**코드를 고쳤을 때** — 이것이 «다시 올리기» 입니다.

```bash
git pull                                              # ← 이것을 빠뜨리면 옛 코드가 올라갑니다
gcloud run deploy cash-flow --source . --region us-central1
```

환경변수는 그대로 남습니다. 다시 적을 필요가 없습니다.

**설정값만 바꿀 때** — 주소나 비밀번호 같은 것.

```bash
gcloud run services update cash-flow --region us-central1 \
  --update-env-vars KEYSERVER_URL=https://script.google.com/macros/s/.../exec
```

### `--set-` 과 `--update-` 도 다릅니다

**한 번 데였습니다.**

| | 하는 일 |
|---|---|
| `--set-env-vars` | 적어 준 것으로 **통째로 갈아엎습니다.** 안 적은 것은 지워집니다 |
| `--update-env-vars` | 적어 준 것만 바꾸고 **나머지는 그대로** 둡니다 |

`deploy/올리기.sh` 가 `--set-` 을 쓰고 있었습니다. 그 스크립트는 버킷과 접속
코드만 적어 주므로, 따로 넣어 두신 `KEYSERVER_URL` 과 `KEYSERVER_PASSWORD` 가
**돌릴 때마다 조용히 지워졌습니다.** 키를 발급해도 구글 시트 장부에 안 올라가고
메일도 안 나가는데, 배포 화면은 한 마디도 하지 않았습니다.

지금은 `--update-` 를 쓰고, 올린 뒤에 키 서버가 연결돼 있는지 확인해 말해 줍니다.

### 이 둘은 다릅니다

한 번 데였습니다. 코드를 고쳐 저장소에 올린 뒤 `services update` 만 돌렸더니,
환경변수는 바뀌었는데 **코드는 옛 판 그대로**였습니다. 고객에게 나가는 메일이
예전 모양으로 계속 나갔고, 어디가 잘못인지 한참 못 찾았습니다.

| 무엇을 고쳤나 | 무엇을 도나 |
|---|---|
| 파이썬·화면 코드 | `git pull` → `gcloud run deploy --source .` |
| 주소·비밀번호 같은 설정값 | `gcloud run services update --update-env-vars …` |
| 앱스 스크립트(메일 보내는 쪽) | 구글 편집기에 다시 붙여넣기 → [배포 관리] → 새 버전 |

셋은 **각각 따로** 올라갑니다. 하나를 올렸다고 나머지가 따라오지 않습니다.

`bash deploy/올리기.sh` 를 쓰시면 폴더가 낡았을 때 먼저 말려 줍니다.

---

## 8. 내리기

```bash
gcloud run services delete cash-flow --region us-central1
```

버킷은 남습니다. 지우시려면 `gcloud storage rm -r gs://cashflow-state`.
