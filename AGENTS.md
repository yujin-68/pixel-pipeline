# AGENTS.md

사용법·파라미터는 `README.md`를 읽으세요. 여기엔 에이전트용 규칙만 있습니다.

## 과금 주의

- `run.py`는 실행 1회당 ApiFrame + PixelLab 크레딧을 씁니다. 사용자 돈입니다.
- 실제 호출(`--count N`)은 사용자가 명시적으로 요청할 때만 하세요. 확인 없이 돌리지 마세요.
- 검증은 무료 경로로 끝내세요: `python run.py --dry-run --count 3`, `python test_pipeline.py`

## swatch.png는 사용자만 줍니다

- 레포에 없습니다. 대신 만들거나 아무 이미지나 받아오지 마세요. 없으면 사용자에게 요청하세요.

## 수정 범위

- 게임별 값(테마/스타일/swatch/API 파라미터)은 `config.toml`에만 둡니다. `run.py`에 하드코딩하지 마세요.
- `[apiframe]` / `[pixellab]` 테이블은 각 API 바디로 그대로 전달됩니다. 필드 추가에 코드 수정이 필요 없습니다.
