"""런타임 설정 — 환경변수 로딩, 경로, 상수.

숫자 임계값·가중치는 여기 두지 않는다 (config/*.yaml). 여기는 인프라 설정만.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# ─────────────────────────── 경로 ───────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"

load_dotenv(BASE_DIR / ".env")


def _path_env(name: str, default: str) -> Path:
    return Path(os.getenv(name, str(BASE_DIR / default))).expanduser()


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:  # 미설정 또는 빈 문자열(`DRY_RUN=`) → 안전한 기본값
        return default
    return raw in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    """프로세스 시작 시 1회 로드되는 불변 설정."""

    # 실행 모드
    mode: str  # paper | live
    dry_run: bool
    universe: str  # SP500 | NASDAQ100 | combined

    # 경로
    state_dir: Path
    output_dir: Path
    cache_dir: Path
    log_level: str

    # LLM (3a-9 이후 사용) — 온도는 config/agents.yaml 의 에이전트별 값
    deepseek_api_key: str | None
    model: str

    # 금융 데이터 API
    fmp_api_key: str | None
    fred_api_key: str | None
    manual_ism_pmi: float | None

    # 알림
    mattermost_webhook_url: str | None
    # 채널별 웹훅 (선택) — 없으면 기본 URL + 텍스트 태그. 기본 웹훅이 채널 고정이라 payload
    # channel 오버라이드는 불가 (report/phase-3 §6, 2026-09 확인).
    mattermost_webhook_research: str | None
    mattermost_webhook_decisions: str | None
    mattermost_webhook_alerts: str | None

    # 캐시 / 페이퍼 브로커
    cache_ttl_hours: int
    paper_commission_pct: float
    paper_fx_spread_pct: float
    monthly_contribution_krw: float  # 적금형 월 납입 (0 = 납입 없음)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """캐시된 설정 싱글턴."""
    manual_ism = os.getenv("MANUAL_ISM_PMI") or ""
    return Settings(
        mode=os.getenv("MODE", "paper"),
        dry_run=_bool_env("DRY_RUN", True),
        universe=os.getenv("UNIVERSE", "combined"),
        state_dir=_path_env("STATE_DIR", "state"),
        output_dir=_path_env("OUTPUT_DIR", "outputs"),
        cache_dir=_path_env("CACHE_DIR", "data/cache"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY"),
        model=os.getenv("MODEL", "deepseek/deepseek-chat"),
        fmp_api_key=os.getenv("FMP_API_KEY"),
        fred_api_key=os.getenv("FRED_API_KEY"),
        manual_ism_pmi=float(manual_ism) if manual_ism else None,
        mattermost_webhook_url=os.getenv("MATTERMOST_WEBHOOK_URL"),
        mattermost_webhook_research=os.getenv("MM_WEBHOOK_RESEARCH"),
        mattermost_webhook_decisions=os.getenv("MM_WEBHOOK_DECISIONS"),
        mattermost_webhook_alerts=os.getenv("MM_WEBHOOK_ALERTS"),
        cache_ttl_hours=int(os.getenv("CACHE_TTL_HOURS", "24")),
        paper_commission_pct=float(os.getenv("PAPER_COMMISSION_PCT", "0.001")),
        paper_fx_spread_pct=float(os.getenv("PAPER_FX_SPREAD_PCT", "0.005")),
        monthly_contribution_krw=float(os.getenv("MONTHLY_CONTRIBUTION_KRW", "100000")),
    )


def ensure_runtime_dirs() -> None:
    """state/ outputs/ data/cache/ 생성 (볼륨 마운트 전 첫 실행 대비)."""
    s = get_settings()
    for d in (s.state_dir, s.output_dir, s.cache_dir):
        d.mkdir(parents=True, exist_ok=True)
