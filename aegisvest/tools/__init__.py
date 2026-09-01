"""Layer 0 결정론 툴 — 숫자를 생성하는 유일한 계층. 계약: docs/TOOLS.md.

툴은 순수 함수 `def <name>(...) -> <Model> | ToolError`. CrewAI BaseTool 래퍼는 3a-9.
호출: `from aegisvest.tools.market_data import market_data` (모듈명 = 함수명이므로
패키지에서 재export 하지 않는다 — 서브모듈 shadowing 방지).
"""
