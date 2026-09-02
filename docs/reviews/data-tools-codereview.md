# Pre-Phase-4 감사 pass 5a — 데이터 툴 독립 `/code-review` (high)

`tools/macro_data.py` · `market_data.py` · `fundamentals.py` · `news.py` · `_io.py` ·
`_prices.py` · `indicators.py`. 5건 전부 수정.

## 수정

| # | 위치 | 문제 | 수정 |
|---|---|---|---|
| 1 | `_prices.py:23` | `history()` 가 `df[cols].dropna()` (how='any') → Close 는 유효한데 장 직후 Volume=NaN 인 최신 봉을 통째로 버림 → `last_price`/`as_of` 가 하루 stale → watchdog 이 하루 지난 가격으로 손절·낙폭 판정 | `dropna(subset=["Close"])`. `market_data` 는 `volume.iloc[-1]` NaN 가드 추가 |
| 2 | `_io.py:68` | `cached_json`/`cached_text` 가 손상 캐시에서 복구 못 함(`cached()` pickle 경로와 달리) + 비원자적 쓰기 → SIGKILL·디스크풀 시 truncate 파일이 TTL(24h) 동안 'fresh' 로 남아 매 호출 예외 | `_write_atomic` (temp+os.replace) 공용. 읽기 실패는 `contextlib.suppress` 로 재생성 |
| 3 | `fundamentals.py:66` | `_cagr` 가 None 을 걸러 리스트 압축 후 `vals[years]` 위치 인덱스 → 매출 시계열 중간 결측 시 기준 연도가 어긋나 잘못된 CAGR → MID 하드필터(`rev_cagr_3y`)·Rule of 40 오판정 | 위치 인덱스 유지, `latest_first[years]` 가 None 이면 계산 불가로 None 반환 |
| 4 | `news.py:52` | `_parse_rss` 가 pubDate 파싱 실패 항목을 `days` 컷오프 무시하고 포함 (`if published and ...`) → `<dc:date>` 등 네임스페이스 날짜의 오래된 기사가 최근으로 오염 | `dc:date`·Atom `published/updated` 폴백 태그 추가 + 날짜 못 읽으면 **제외** |
| 5 | `macro_data.py:140` | `_Yf._vix/_vix3m/_spx` 가 예외 아닌 "빈약한 프레임" 경로에서 값은 None 으로 두면서 `stale_fields` 에 안 넣음 → regime 은 VIX 1일 급등 가드를 조용히 스킵, 소비자는 완전한 레짐 판독으로 오인 | `len(h) < 2` / `h.empty` 도 `stale.append` |

## Round 2 — 0건

- `dropna(subset=["Close"])` 후 최신 봉 H/L/V NaN → `atr`·`vol_ratio` 가 그날만 None
  (`indicators._last_float` 처리) — "전부 stale" 보다 나음. 드묾 (장 마감 ~1h 내 실행 시).
- `cached_json` 이 `read_bytes()` 로 전환 — `json.loads` 가 bytes 수용, UnicodeDecodeError 불가.
- news `dc:date` 는 피드가 `xmlns:dc` 선언 시 ET 가 `{ns}date` 로 확장 — 실 피드도 그러함.

## 검증
- ruff / ruff format / mypy(50) / pytest **268 passed, 2 deselected**
- 신규 테스트 5: CAGR 위치인덱스·미상날짜 제외·dc:date 폴백·손상캐시 재생성·빈약 VIX stale
- 커밋: `fix(data-tools): 독립 code-review 5건 (stale 가격·캐시 손상·CAGR 결측·미상날짜 뉴스·VIX stale)`
