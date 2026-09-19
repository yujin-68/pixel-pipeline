# pixel-pipeline

레퍼런스 이미지 한 장으로 **일관된 화풍의 픽셀 스프라이트를 자동 양산**하는 파이프라인입니다.

```
swatch(레퍼런스)  ->  프롬프트 변주  ->  gpt-image-2 (ApiFrame)  ->  PixelLab 픽셀화  ->  로컬 저장
   화풍 고정          테마 목록 순환        고해상도 원본 생성        원본을 그대로 도트로      out/pixel/*.png
```

핵심은 마지막 단계입니다. PixelLab에 **`init_image_strength = 999`(최대치)** 로 넘기기 때문에
새로 그리는 것이 아니라 **들어간 원본을 그대로 픽셀화**합니다. 그래서 그림의 정체성은 앞단(레퍼런스 +
프롬프트)이 정하고, PixelLab은 도트로 옮기는 일만 합니다.

- 게임에 맞춘 값은 전부 `config.toml`에 있습니다. `run.py`는 건드릴 일이 없습니다.
- 파일 하나(`run.py`), 의존성 세 개(`requests` / `pillow` / `python-dotenv`)입니다.

## 필요한 것

- Python **3.11 이상** (설정 파싱에 표준 라이브러리 `tomllib`을 사용합니다)
- [ApiFrame](https://apiframe.ai) API 키 — gpt-image-2 호출용
- [PixelLab](https://pixellab.ai) API 토큰 — 픽셀화용 (유료 구독이 필요합니다)

두 서비스 모두 **호출할 때마다 크레딧이 나갑니다.** 돌리기 전에 아래 "비용" 절을 읽어주세요.

## 설치

```bash
git clone <이 저장소>
cd pixel-pipeline
pip install -r requirements.txt

cp .env.example .env     # Windows: copy .env.example .env
# .env 를 열어 키 두 개를 채웁니다
```

## 준비: swatch 한 장

원하는 화풍의 이미지 한 장을 `swatch.png`로 저장합니다. 이 이미지가 색감·질감·톤을 잡는 기준이 됩니다.
실행할 때 ApiFrame에 자동 업로드되므로 **따로 호스팅할 필요가 없습니다.**
이미 공개 URL이 있다면 `config.toml`의 `swatch`에 그 URL을 적으면 업로드를 건너뜁니다.

> 좋은 swatch는 만들려는 것과 같은 시점·같은 조명·같은 채도의 예시 한 장입니다.
> 한 장이 화풍을 잡고, 다양성은 프롬프트(`subjects`)가 만듭니다.

## 실행

```bash
python run.py --dry-run --count 3   # 무료입니다. 어떤 프롬프트로 어떤 요청이 나갈지만 출력합니다
python run.py --count 1             # 실제 1장 (먼저 이것으로 결과를 확인하세요)
python run.py --count 10            # 마음에 들면 양산합니다
```

결과물입니다.

```
out/raw/000_narrow-two-story-ramen-noodle-shop.png     # gpt-image-2 원본
out/pixel/000_narrow-two-story-ramen-noodle-shop.png   # 픽셀화 + 배경 투명 (최종물)
```

번호는 기존 파일 다음부터 이어 붙습니다. 다시 돌려도 덮어쓰지 않습니다.
원본(`raw/`)도 남기는 이유는, 결과가 이상할 때 **생성이 문제인지 픽셀화가 문제인지** 바로 갈라 보기 위해서입니다.

## 내 게임에 맞게 바꾸기

`config.toml`에서 세 자리만 바꾸면 완전히 다른 소재로 돌아갑니다. 기본값은 실제로 검증한
"사이버펑크 상점 건물" 프리셋이니, 그 위에 덮어쓰시면 됩니다.

| 자리 | 하는 일 | 예 |
|---|---|---|
| `swatch` | 화풍 고정 (로컬 파일 또는 CDN URL) | `"swatch.png"` |
| `subjects` | **변주 축.** 한 줄에 하나, 순서대로 순환합니다 | `"narrow two-story ramen noodle shop"` |
| `style` | 모든 이미지 공통 문장. 시점·재질·금지 요소를 담습니다 | `"... orthographic, no perspective, ..."` |

프롬프트는 `"{subjects[i]}, {style}"` 로 조립됩니다. gpt-image-2에는 seed나 레퍼런스 강도 조절이
없어서, **다양성은 오직 `subjects`에서 나옵니다.** 결과가 다 비슷하다면 테마 문장을 더 벌려서 써주세요.

`style`을 쓸 때 도움이 되는 점들입니다.
- 픽셀로 표현되지 않는 묘사(표정, 분위기)는 빼세요. 자리만 차지합니다.
- 원하지 않는 요소는 금지어로 박아주세요 (`no perspective`, `no side walls`).
- 적지 않으면 매번 갈리는 것(간판 언어 등)은 명시해주세요 (`all signage text in English`).

## 파라미터

**`[pixellab]` 테이블에 적은 키는 그대로 PixelLab 요청 바디가 됩니다.** 필드를 추가해도 코드를 고칠 필요가 없습니다.
([`/create-image-pixflux`](https://api.pixellab.ai/v2/openapi.json)의 모든 필드를 쓸 수 있습니다)

| 키 | 설명 |
|---|---|
| `init_image_strength` | **1~999.** 999는 원본을 최대한 그대로 픽셀화합니다. 낮추면 PixelLab이 자기 해석을 섞습니다 |
| `image_size` | 최대 400×400. 픽셀 스프라이트의 실제 해상도입니다. **원본은 이 크기로 자동 축소해서 보냅니다**(PixelLab이 크기가 다르면 거부합니다) — `[apiframe] aspect_ratio`와 비율을 맞춰주세요, 다르면 찌그러집니다 |
| `view` | `side` / `low top-down` / `high top-down` |
| `description` | 원본이 지배하므로 일반적인 문장이면 충분합니다. 테마별로 바꿀 필요가 없습니다 |
| `seed` | 넣으면 같은 입력에 같은 결과가 나옵니다 (재현용) |
| `direction`, `outline`, `shading`, `detail`, `no_background` | 필요하면 추가하세요 |

`[apiframe]` 테이블도 같은 방식으로 `gptImage2Params`가 됩니다
(`quality`, `aspect_ratio`, `output_format`, `number_of_images` 등).

### 결과가 뭉개질 때

1. `init_image_strength`를 600~800으로 낮춰보세요
2. `image_size`를 키워보세요 (최대 400)
3. `style`에 `plain white background`, `flat 2D sprite`처럼 평면성을 강제하는 말을 더 넣어보세요

## 배경 제거

PixelLab은 200px를 넘는 이미지에 투명 배경을 주지 않습니다. 그래서 흰 배경을 코드로 없앱니다.
**캔버스 가장자리에 닿은 흰 영역만** 지우므로, 간판 글씨 같은 스프라이트 *안쪽* 흰색은 살아남습니다.

```toml
[background]
remove = true
threshold = 230   # 배경이 누런 편이면 낮춰주세요
```

작은 사이즈라 PixelLab의 `no_background`를 쓰신다면 `remove = false`로 꺼주세요.

## 비용

- **PixelLab 픽셀화는 호출당 크레딧이 나갑니다.** `--count` 없이 무한 루프를 돌리지 마세요.
- 실행할 때마다 양쪽 잔액을 먼저 출력하고, PixelLab 잔액이 0이면 시작하지 않습니다.
- 먼저 `--dry-run`으로 프롬프트를 확인하고, `--count 1`로 한 장 본 뒤에 양산하시길 권합니다.

## 하지 않는 것

품질 검증 게이트, manifest 기록, 엔진 임포트는 없습니다. 파이프라인은 **저장까지**입니다.
고르는 것은 사람이 `out/pixel/`을 보고 합니다.

## 자체 점검

```bash
python test_pipeline.py    # 네트워크 없이 도는 assert 4개
```

## 라이선스

MIT입니다. 생성된 이미지의 권리는 각 API 서비스의 약관을 따릅니다.
