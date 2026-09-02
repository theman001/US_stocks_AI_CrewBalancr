# ponytail-audit 정리 (2026-09-02)

정확성 감사 7패스 후 오버엔지니어링 스캔(`ponytail-audit`). 죽은 코드·config·의존성 제거.
**동작 변화 없음** — 전부 아무도 안 쓰던 것. 276 tests 그대로.

## 제거

| 대상 | 이유 |
|---|---|
| 레거시 `paper_portfolio.json` 이관/폴백 (`main._load_shadow` old-format, `report._load_org_pf` 폴백, `pipeline._demo`) | 미배포 → 레거시 파일 존재 불가. `shadow.json` 만. |
| `Settings.{reasoner_model, llm_temperature, llm_max_rpm}` + `get_llm(reasoner=)` 파라미터·죽은 브랜치 | 아무도 `reasoner=True` 안 넘김. temperature 는 `config/agents.yaml` 에이전트별 값을 항상 명시 전달. `get_llm(*, temperature: float)` 로 축소 |
| `Settings.max_high_risk_exposure` + `MAX_HIGH_RISK_EXPOSURE` | 코드 사용 0. 실제 캡은 `config/allocation.yaml guardrails.high_abs_cap` |
| `Settings.nasdaq_data_link_api_key` + `NASDAQ_DATA_LINK_API_KEY` | 사용 0. Sharadar 백테스트(3a-11 보류) 착수 시 재추가 |
| `schemas.Verdict` StrEnum | `test_scaffolding` 만 참조. verdict 필드는 전부 bare `str` |
| `schemas.Metric` 모델 | "모든 숫자는 이 형태로 출처를 남긴다" 인데 인스턴스화 0. `no_fabricated_numbers` 가드레일이 대체 |
| `.env.example`: `FRED_SERIES_{WEI,CLAIMS,HY_OAS,YC}`, `MANUAL_ISM_PMI_ASOF`, `LLM_TEMPERATURE`, `LLM_MAX_RPM`, `REASONER_MODEL` | 읽는 코드 0 (FRED ID 는 `macro_data.py` 하드코딩) |
| `agents/tools.py` `NEWS`/`FUNDAMENTALS`/`TECHNICAL` 별칭 | `crew._AGENT_TOOLS` 가 `news_scraper_tool` 등 직접 참조 |
| **의존성**: `requests-cache` (`_io.py` 가 직접 구현), `crewai-tools` (툴 데코는 `crewai.tools`, core 번들) | crewai-tools 제거로 transitive ~10개 동반 제거 (pymupdf·pytube·tiktoken·python-docx·youtube-transcript-api·defusedxml 등) |

## 유지 (검토했으나 정당)

- `_dc_*`/`_DIARY` dict-dispatch — ruff PLR0912 가 강제한 형태, 에이전트별 실제 변환 로직
- `rules.py` pydantic + lru_cache — YAML 섹션 1:1, 적절
- `_screen._OPS` 딕트 디스패치 — 7개 연산자, 과하지 않음
- 모듈별 `main()`/`_demo()` — cron 엔트리포인트 (`python -m aegisvest.watchdog` 등)

## 검증
- `uv sync --all-extras` (transitive 정리) → ruff / format / mypy(50) / pytest **276 passed**
- net: 코드/config ~-60줄, uv.lock -157줄, -2 직접 의존성 (-10 transitive)
- 커밋: `refactor(ponytail): 죽은 config·스키마·레거시 이관 제거 + crewai-tools/requests-cache 의존성 제거`
