"""네트워크 없이 도는 자체 점검.  python test_pipeline.py"""

import tempfile
from pathlib import Path

from PIL import Image

import run


def test_background_keeps_interior_white():
    """배경은 지우고, 스프라이트 안쪽 흰색(간판 글씨)은 남겨야 한다."""
    img = Image.new("RGB", (32, 32), (255, 255, 255))            # 흰 배경
    for x in range(8, 24):
        for y in range(8, 24):
            img.putpixel((x, y), (120, 120, 120))                # 회색 몸통
    for x in range(12, 20):
        for y in range(12, 16):
            img.putpixel((x, y), (255, 255, 255))                # 몸통 안 흰 글씨

    out = run.remove_background(img)
    assert out.getpixel((0, 0))[3] == 0, "테두리 배경이 안 지워졌다"
    assert out.getpixel((31, 31))[3] == 0, "테두리 배경이 안 지워졌다"
    assert out.getpixel((14, 14))[3] == 255, "간판 글씨(내부 흰색)를 먹었다"
    assert out.getpixel((9, 9))[3] == 255, "몸통이 지워졌다"


def test_prompt_cycles_subjects():
    subjects = ["a shop", "a garage"]
    assert run.prompt_for(0, subjects, "flat")[1] == "a shop, flat"
    assert run.prompt_for(1, subjects, "flat")[0] == "a garage"
    assert run.prompt_for(2, subjects, "flat")[0] == "a shop", "테마 순환이 깨졌다"


def test_next_index_continues():
    with tempfile.TemporaryDirectory() as d:
        raw = Path(d)
        assert run._next_index(raw) == 0
        (raw / "000_a.png").touch()
        (raw / "007_b.png").touch()
        assert run._next_index(raw) == 8, "기존 파일을 덮어쓸 번호를 골랐다"


def test_config_loads():
    cfg = run.load_config("config.toml")
    assert cfg["subjects"] and cfg["style"].strip()
    assert cfg["pixellab"]["init_image_strength"] == 999


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all good")
