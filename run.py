"""
pixel-pipeline - 레퍼런스 한 장(swatch)으로 픽셀 스프라이트를 양산한다.

  swatch -> 프롬프트 변주 -> gpt-image-2 (ApiFrame) -> PixelLab 픽셀화 -> out/pixel/*.png

게임에 맞춘 값(테마/스타일/swatch/파라미터)은 전부 config.toml 에 있다. 이 파일엔 없다.

  python run.py --dry-run --count 3   # 호출 없이 프롬프트와 요청 바디만 출력 (무료)
  python run.py --count 5             # 실제 생성
"""

import argparse
import base64
import io
import os
import re
import sys
import time
import tomllib
from pathlib import Path

import requests
from dotenv import load_dotenv
from PIL import Image, ImageChops, ImageDraw

AF = "https://api.apiframe.ai/v2"
PL = "https://api.pixellab.ai/v2"

# flood fill 로 배경을 칠할 임시색. 배경은 near-white 라서 이 색과 겹칠 일이 없다.
_SENTINEL = (255, 0, 255)


def load_config(path: str) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"{name} 가 없습니다. .env.example 을 .env 로 복사해서 채우세요.")
    return value


def _to_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _transient(r, tag: str) -> bool:
    """폴링 루프가 일시적 오류에 죽으면 안 된다. 5xx/429 는 API 사정이지 작업 실패가 아니다."""
    if r.status_code >= 500 or r.status_code == 429:
        print(f"  [{tag}] {r.status_code}, retrying...", end="\r", flush=True)
        return True
    return False


def prompt_for(i: int, subjects: list[str], style: str) -> tuple[str, str]:
    """i 번째 프롬프트. 테마 목록을 순환하며 고정 스타일 문장과 합친다."""
    subject = subjects[i % len(subjects)]
    return subject, f"{subject}, {style}"


def check_balance(af_key: str, pl_token: str):
    """양쪽 잔액을 찍고, PixelLab 이 0 이면 시작 전에 멈춘다. 루프를 돌리기 전에 비용부터 본다."""
    try:
        me = requests.get(f"{AF}/me", headers={"X-API-Key": af_key}, timeout=30).json()
        print(f"ApiFrame credits: {(me.get('team') or {}).get('credits', '?')}")
    except requests.RequestException as e:
        print(f"ApiFrame balance check failed: {e}")

    r = requests.get(f"{PL}/balance", headers={"Authorization": f"Bearer {pl_token}"},
                     timeout=30)
    r.raise_for_status()
    data = r.json()
    gens = (data.get("subscription") or {}).get("generations", 0)
    usd = (data.get("credits") or {}).get("usd", 0)
    print(f"PixelLab: {gens} generations, ${usd}")
    if not gens and not usd:
        sys.exit("PixelLab 잔액이 0 입니다. 충전 후 다시 실행하세요.")


def resolve_swatch(ref: str, af_key: str) -> str:
    """URL 이면 그대로. 로컬 파일이면 ApiFrame 에 올려 CDN URL 을 받는다(1-2시간 유효)."""
    if ref.startswith("http"):
        return ref
    path = Path(ref)
    if not path.exists():
        sys.exit(f"swatch 파일이 없습니다: {path}  (config.toml 의 swatch 를 확인하세요)")
    with path.open("rb") as f:
        r = requests.post(f"{AF}/uploads", headers={"X-API-Key": af_key},
                          files={"file": (path.name, f)}, timeout=120)
    if not r.ok:
        sys.exit(f"[af] upload {r.status_code}: {r.text}")
    url = r.json().get("url")
    print(f"[af] swatch uploaded: {url}")
    return url


def poll_job(job_id: str, af_key: str, max_polls=90, interval=5) -> list[str]:
    for i in range(max_polls):
        r = requests.get(f"{AF}/jobs/{job_id}", headers={"X-API-Key": af_key}, timeout=30)
        if _transient(r, "af"):
            time.sleep(interval)
            continue
        r.raise_for_status()
        data = r.json()
        status = data.get("status", "")
        if status == "COMPLETED":
            print("  [af] completed" + " " * 20)
            return (data.get("result") or {}).get("images") or []
        if status in ("FAILED", "CANCELLED"):
            print(f"  [af] {status}: {data.get('error')}")
            return []
        print(f"  [af] {status} {data.get('progress', '?')}%...", end="\r", flush=True)
        time.sleep(interval)
    print("  [af] timed out")
    return []


def generate(prompt: str, swatch_url: str, params: dict, af_key: str) -> list[str]:
    """gpt-image-2 로 원본 이미지 생성. swatch 가 붙으면 비동기 job 이 되므로 폴링한다."""
    gpt_params = dict(params)
    if swatch_url:
        gpt_params["input_images"] = [swatch_url]
    body = {"model": "gpt-image-2", "prompt": prompt, "gptImage2Params": gpt_params}
    r = requests.post(f"{AF}/images/generate", json=body,
                      headers={"X-API-Key": af_key, "Content-Type": "application/json"},
                      timeout=120)
    if r.status_code == 402:
        sys.exit("ApiFrame 크레딧 소진. 충전 후 다시 실행하세요.")
    if not r.ok:
        print(f"  [af] {r.status_code}: {r.text}")
        return []
    data = r.json()
    if data.get("images"):  # 참조 이미지가 없으면 동기 응답
        return data["images"]
    job_id = data.get("jobId")
    if not job_id:
        print(f"  [af] 알 수 없는 응답: {data}")
        return []
    print(f"  [af] jobId={job_id}")
    return poll_job(job_id, af_key)


def pixelate(img: Image.Image, params: dict, pl_token: str) -> Image.Image | None:
    """PixelLab /create-image-pixflux. 동기 응답이라 폴링이 없다.

    init_image_strength 가 높을수록 원본을 그대로 '픽셀화'한다. config 의 [pixellab] 테이블이
    그대로 바디가 되므로 direction/outline/seed 같은 필드도 코드 수정 없이 추가할 수 있다.
    """
    body = {**params, "init_image": {"type": "base64", "base64": _to_b64(img)}}
    r = requests.post(f"{PL}/create-image-pixflux", json=body,
                      headers={"Authorization": f"Bearer {pl_token}"}, timeout=300)
    if r.status_code == 402:
        sys.exit("PixelLab 크레딧 소진. 충전 후 다시 실행하세요.")
    if not r.ok:
        print(f"  [pl] {r.status_code}: {r.text}")
        return None
    data = r.json()
    b64 = (data.get("image") or {}).get("base64", "")
    if "," in b64:  # data-URL 접두사 제거
        b64 = b64.split(",", 1)[1]
    if not b64:
        print(f"  [pl] 응답에 이미지가 없습니다: {data}")
        return None
    out = Image.open(io.BytesIO(base64.b64decode(b64)))

    size = params.get("image_size") or {}
    want = (size.get("width"), size.get("height"))
    if None not in want and out.size != want:
        # 픽셀 아트는 NEAREST 로만 리사이즈한다. 보간하면 경계가 뭉개진다.
        out = out.resize(want, Image.NEAREST)
    usage = (data.get("usage") or {}).get("usd", "?")
    print(f"  [pl] ok  {out.size[0]}x{out.size[1]}  usage=${usage}")
    return out


def remove_background(img: Image.Image, threshold: int = 230) -> Image.Image:
    """캔버스 가장자리에 닿은 near-white 영역만 투명 처리한다.

    단순 임계값은 스프라이트 *안쪽* 흰색까지 먹는다(간판 글씨에 구멍이 난다). 배경은
    '가장자리와 연결된' near-white 영역뿐이므로 테두리에서만 flood fill 한다.
    PixelLab 의 no_background 는 200px 를 넘으면 적용되지 않아서 이 단계가 필요하다.
    """
    flat = img.convert("RGB")
    filled = flat.copy()
    w, h = filled.size
    border = ([(x, y) for x in range(w) for y in (0, h - 1)]
              + [(x, y) for y in range(h) for x in (0, w - 1)])
    tolerance = 3 * (255 - threshold)  # floodfill 의 thresh 는 채널 차이의 합
    for seed in border:
        if min(filled.getpixel(seed)) >= threshold:
            ImageDraw.floodfill(filled, seed, _SENTINEL, thresh=tolerance)
    mask = ImageChops.difference(filled, flat).convert("L").point(lambda v: 0 if v else 255)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def _next_index(raw_dir: Path) -> int:
    """기존 파일 다음 번호. 재실행해도 덮어쓰지 않는다."""
    nums = [int(m.group(1)) for f in raw_dir.glob("*.png")
            if (m := re.match(r"(\d+)_", f.name))]
    return max(nums, default=-1) + 1


def main():
    parser = argparse.ArgumentParser(
        description="swatch -> gpt-image-2 -> PixelLab -> 로컬 저장")
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--count", type=int, help="생성 횟수 (config 의 count 를 덮어씀)")
    parser.add_argument("--dry-run", action="store_true",
                        help="API 호출 없이 프롬프트와 요청 바디만 출력")
    args = parser.parse_args()

    cfg = load_config(args.config)
    subjects, style = cfg["subjects"], cfg["style"].strip()
    count = args.count or cfg.get("count", 1)
    out = Path(cfg.get("out_dir", "out"))
    raw_dir, pixel_dir = out / "raw", out / "pixel"
    af_params, pl_params = cfg.get("apiframe", {}), cfg.get("pixellab", {})
    bg = cfg.get("background", {})

    if args.dry_run:
        for i in range(count):
            subject, prompt = prompt_for(i, subjects, style)
            print(f"\n[{i}] {subject}\n  {prompt}")
        gpt = dict(af_params)
        if cfg.get("swatch"):
            gpt["input_images"] = [cfg["swatch"]]
        print(f"\napiframe gptImage2Params: {gpt}")
        print(f"pixellab body: {pl_params} + init_image=<base64 png>")
        return

    load_dotenv()
    af_key, pl_token = _require("APIFRAME_API_KEY"), _require("PIXELLAB_TOKEN")
    check_balance(af_key, pl_token)
    swatch = resolve_swatch(cfg["swatch"], af_key) if cfg.get("swatch") else ""

    raw_dir.mkdir(parents=True, exist_ok=True)
    pixel_dir.mkdir(parents=True, exist_ok=True)
    index = _next_index(raw_dir)
    for i in range(count):
        subject, prompt = prompt_for(i, subjects, style)
        print(f"\n{'=' * 60}\n[{index:03d}] {subject}\n{'=' * 60}")
        urls = generate(prompt, swatch, af_params, af_key)
        if not urls:
            print("  생성 실패, 건너뜀")
            continue

        for url in urls:
            name = f"{index:03d}_{_slug(subject)}.png"
            index += 1
            resp = requests.get(url, timeout=120)
            resp.raise_for_status()
            src = Image.open(io.BytesIO(resp.content)).convert("RGB")
            src.save(raw_dir / name)
            print(f"  saved {raw_dir / name}")

            px = pixelate(src, pl_params, pl_token)
            if px is None:
                print("  픽셀화 실패, 건너뜀")
                continue
            if bg.get("remove", True):
                px = remove_background(px, bg.get("threshold", 230))
            px.save(pixel_dir / name)
            print(f"  saved {pixel_dir / name}")

    print(f"\n끝. -> {pixel_dir}")


if __name__ == "__main__":
    main()
