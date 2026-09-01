"""`python -m aegisvest.diary <cmd>` 디스패처. report/phase-4 §8·§10.

- `review` → 거버넌스 (분기 인간 검토). 채점·반성·색인 배치는 각 모듈:
  `python -m aegisvest.diary.{evaluate,reviewer,rag}`.
"""

from __future__ import annotations

import argparse
import logging

from aegisvest.config import get_settings
from aegisvest.diary import governance


def main() -> None:
    logging.basicConfig(
        level=get_settings().log_level, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    p = argparse.ArgumentParser(prog="python -m aegisvest.diary")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("review", help="판단 일기 거버넌스 리포트 / 액션 (§8)")
    r.add_argument("--approve", metavar="ID", help="pending_review → approved")
    r.add_argument("--retire", metavar="ID", help="검색 제외 (다음 rag 배치가 벡터 삭제)")
    r.add_argument("--edit", metavar="ID", help="교훈 수정 (--lesson 필수)")
    r.add_argument("--lesson", help="--edit 대상의 새 lesson 문구")
    r.add_argument("--lesson-card", help="--edit 대상의 새 lesson_card (선택)")
    r.add_argument("--ack-tags", action="store_true", help="pending_tags.json 검토 완료 처리")
    a = p.parse_args()

    if a.cmd == "review":
        governance.run_cli(
            approve_id=a.approve,
            retire_id=a.retire,
            edit_id=a.edit,
            lesson=a.lesson,
            lesson_card=a.lesson_card,
            ack_tags=a.ack_tags,
        )


if __name__ == "__main__":
    main()
