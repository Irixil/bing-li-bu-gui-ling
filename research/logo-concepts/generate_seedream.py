#!/usr/bin/env python3
"""Generate three Q版山羊 logo character explorations with Volcengine Seedream.

The API key is read only from ARK_API_KEY or VOLCENGINE_API_KEY.
Nothing in this file contains a credential.
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import subprocess
import urllib.request


ENDPOINT = os.getenv("ARK_ENDPOINT", "https://ark.cn-beijing.volces.com/api/v3/images/generations")
MODEL = os.getenv("SEEDREAM_MODEL", "doubao-seedream-4-0-250828")
OUT_DIR = pathlib.Path(__file__).parent / "seedream"

COMMON = """Use case: logo-brand. Create a lovable Q版 Chinese goat mascot for an elderly health-recording app called 病历不归零. The mascot should feel warm, trustworthy, companionable, and memorable rather than childish. Round face, big kind eyes, small body, short legs, soft cream wool, rounded curved horns, gentle smile, clean polished character design, soft 3D illustration with subtle paper-like texture, warm white background with a very light lavender and apricot halo, blue-violet and warm apricot accents, centered single character, generous margins, app-icon friendly. No words, no letters, no Chinese characters, no watermark, no hospital cross, no stethoscope, no medical needles, no scary expression, no sharp aggressive horns, no extra characters, no busy background."""

PROMPTS = {
    "01-陪伴山羊": COMMON + " Make this version especially cuddly: the goat hugs a small rounded blank record card close to its chest, with tiny hooves visible. The card is blank and contains no symbols or text.",
    "02-元气山羊": COMMON + " Make this version especially cheerful and cute: the goat sits with one tiny hoof raised in a friendly wave, rosy cheeks, a small warm apricot scarf, lively but calm expression.",
    "03-安心山羊": COMMON + " Make this version especially calm and reassuring: the goat sits inside a rounded lavender bean-shaped cushion, ears slightly lowered, soft sleepy smile, cozy companion feeling.",
}


def api_key() -> str:
    value = os.getenv("ARK_API_KEY") or os.getenv("VOLCENGINE_API_KEY")
    if not value:
        key_file = pathlib.Path("/tmp/codex_seedream_key")
        if key_file.exists():
            value = key_file.read_text().strip()
    if not value:
        try:
            value = subprocess.check_output(
                ["security", "find-generic-password", "-s", "codex-seedream", "-w"],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
        except (FileNotFoundError, subprocess.CalledProcessError):
            value = ""
    if not value:
        raise SystemExit("请先设置 ARK_API_KEY/VOLCENGINE_API_KEY，或将 Key 存入 macOS 钥匙串服务 codex-seedream。")
    return value


def request_image(prompt: str) -> dict:
    body = {
        "model": MODEL,
        "prompt": prompt,
        "size": "2K",
        "response_format": "url",
        "watermark": False,
    }
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def save_result(name: str, result: dict) -> pathlib.Path:
    item = (result.get("data") or [{}])[0]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    output = OUT_DIR / f"{name}.png"
    if item.get("b64_json"):
        output.write_bytes(base64.b64decode(item["b64_json"]))
    elif item.get("url"):
        with urllib.request.urlopen(item["url"], timeout=180) as response:
            output.write_bytes(response.read())
    else:
        raise RuntimeError(f"Seedream 返回中没有图片 URL 或 b64_json：{result}")
    return output


def main() -> None:
    print(f"model={MODEL}")
    for name, prompt in PROMPTS.items():
        print(f"generating {name} ...")
        result = request_image(prompt)
        path = save_result(name, result)
        print(path)


if __name__ == "__main__":
    main()
