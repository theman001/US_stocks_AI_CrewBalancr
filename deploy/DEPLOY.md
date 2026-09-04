# 배포 — Radxa Rock 5 ITX / Debian / OMV8

**모델**: 이미지는 GitHub Actions 가 GHCR 에 빌드·게시. Radxa 는 pull 만.
OMV8 `openmediavault-compose` 에 `docker-compose.yml` **한 파일**만 붙여넣고 Up.
repo·Dockerfile·crontab 을 보드에 얹을 필요 없음.

```
push → GH Actions (.github/workflows/docker-publish.yml, arm64 네이티브 러너)
     → ghcr.io/theman001/aegisvest:latest
     → OMV-compose: Pull → Up  (supercronic 이 cron 대기, restart=unless-stopped)
```

---

## 0. 사전 (1회)

### 0.1 GHCR 패키지 공개
첫 Actions 성공 후 GitHub → 프로필 **Packages → aegisvest → Package settings →
Change visibility → Public**. (안 하면 Radxa 에서 `docker login ghcr.io` 필요.)

### 0.2 OMV 공유폴더
OMV → 스토리지 → 공유폴더 → `aegisvest` 생성. 절대경로 확인 (예:
`/srv/dev-disk-by-uuid-abcd.../aegisvest`). 이게 `.env` 의 `AEGIS_DATA`.

### 0.3 API 키
- **DeepSeek**: 잔액 확인 (크루 필수)
- **FRED**: https://fred.stlouisfed.org/docs/api/api_key.html (무료, 즉시)
- FMP·Mattermost 웹훅: 선택

---

## 1. 첫 배포

### 1.1 이미지 확인
Actions 탭에서 `docker image (ghcr, arm64)` 워크플로가 초록. Packages 에
`aegisvest` 패키지 존재 + `latest` 태그.

### 1.2 OMV-compose 스택 등록
OMV → 서비스 → Compose → Files → **＋(추가)**:
- Name: `aegisvest`
- 내용: repo 의 `docker-compose.yml` 전체 붙여넣기

### 1.3 Environment
같은 화면 Environment 탭 (또는 스택 옆 톱니 → Edit env). repo 의 `.env.example`
기준으로 채운다. **최소**:

```bash
AEGIS_DATA=/srv/dev-disk-by-uuid-XXXX/aegisvest
TZ=Asia/Seoul
DRY_RUN=false
DEEPSEEK_API_KEY=sk-...
FRED_API_KEY=...
```

RAM 8GB 미만 보드면 `AEGIS_MEM=3g` 등으로 낮추고 zram/swap 확보.

### 1.4 기동
스택 선택 → **Up**. OMV 가 `docker compose pull && up -d` 실행.
- 컨테이너 `aegisvest` Running, 로그에 `supercronic ... /app/deploy/crontab` +
  다음 잡까지 대기.
- `${AEGIS_DATA}/{state,outputs,logs,cache}` 디렉터리 자동 생성.

---

## 2. 스케줄 (KST, `deploy/crontab`)

| 잡 | 시각 | 내용 |
|---|---|---|
| 감시견 | 매일 06:30 | 매크로 점수 누적 · 위기 감지 · 일일 NAV 마킹 |
| 주간 크루 | 일 22:00 | 파이프라인 → 9 에이전트 → 체결 → 리포트 |
| 일기 배치 | 월 23:00 | 채점 → ⑨ 반성 → RAG 색인 |

첫 주는 데이터가 얇아 크루가 대부분 결정론 코어로 수렴. bge-m3(~2.3GB)는 일기
코퍼스가 `_MIN_CORPUS`(5) 넘는 시점(수 주 후) 첫 회상·색인 때 1회 다운로드 →
`hf-cache` 볼륨에 영구.

---

## 3. 운영

### 확인
```bash
docker logs -f aegisvest                         # supercronic 잡 로그
ls ${AEGIS_DATA}/outputs/                         # 주간 리포트 markdown
docker exec aegisvest python -m aegisvest.report performance   # 성과 CLI
cat ${AEGIS_DATA}/state/shadow.json | jq .organization.history[-1]
```

### 수동 실행 (테스트)
```bash
docker exec aegisvest python -m aegisvest.watchdog
docker exec -e DRY_RUN=true aegisvest python -m aegisvest.main   # 무접촉 리허설
```

### 갱신
`main` 에 push → Actions 자동 빌드. OMV-compose 에서 스택 → **Pull → Up**
(또는 `docker compose -p aegisvest pull && up -d`). `hf-cache`·`state` 볼륨 유지.

### 리허설 ↔ 가동 전환
`.env` 의 `DRY_RUN` 만 토글 후 Up. `true` = state/ 무접촉·미체결·알림 스킵.

---

## 4. 트러블슈팅

| 증상 | 원인 / 조치 |
|---|---|
| `pull access denied` | GHCR 패키지 비공개 → 0.1, 또는 Radxa 에서 `echo $PAT \| docker login ghcr.io -u theman001 --password-stdin` |
| `AEGIS_DATA 미설정` 에러 | Environment 에 `AEGIS_DATA` 절대경로 |
| 컨테이너 OOM-kill (RAG 배치) | `AEGIS_MEM` 상향 또는 swap. 8GB↑ 권장 |
| Actions 빌드 느림 (~15분) | QEMU 크로스빌드. 속도 원하면 `runs-on: ubuntu-24.04-arm` (네이티브, public repo 무료) + `setup-qemu-action` 제거 |
| 크루가 매번 결정론으로 수렴 | `DEEPSEEK_API_KEY` 누락/잔액 부족 — `docker logs` 에 `DEEPSEEK_API_KEY 없음` |
| 알림 안 옴 | `MATTERMOST_WEBHOOK_URL` 미설정이면 정상 (로그·outputs/ 만). `DRY_RUN=true` 여도 스킵 |

---

## 5. 로컬에서 이미지 빌드 (선택)

```bash
docker build -t aegisvest:local .
docker compose -f docker-compose.yml up -d   # image 줄을 aegisvest:local 로 바꾸고
```
