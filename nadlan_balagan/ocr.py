#!/usr/bin/env python3
"""Read a four-digit number from a PNG or JPG using Tesseract OCR."""

import argparse
from io import BytesIO
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from PIL import Image, ImageFilter


def tesseract_binary() -> str:
    """Find Tesseract on either OS, with an override for non-PATH installs."""
    configured = os.environ.get("NADLAN_TESSERACT")
    if configured:
        if Path(configured).is_file():
            return configured
        raise RuntimeError(f"NADLAN_TESSERACT does not exist: {configured}")
    found = shutil.which("tesseract")
    if found:
        return found
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
            if base:
                candidate = Path(base) / "Tesseract-OCR" / "tesseract.exe"
                if candidate.is_file():
                    return str(candidate)
    raise RuntimeError("Tesseract OCR is not installed or not on PATH")


def read_four_digits(png_path: str | Path | None = None) -> str:
    """Return the four digits in a PNG or JPG, preserving any leading zero.

    If png_path is None, read one path from standard input.
    """
    if png_path is None:
        png_path = sys.stdin.readline().rstrip("\r\n")
    if not png_path:
        raise ValueError("No image path was provided")

    image_path = Path(png_path).expanduser()
    if not image_path.is_file():
        raise FileNotFoundError(f"Image file not found: {image_path}")
    if image_path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        raise ValueError(f"Expected a PNG or JPG file: {image_path}")
    env = os.environ.copy()
    tesseract_bin = tesseract_binary()

    def recognize(source: str | bytes, psm: int) -> str:
        result = subprocess.run(
            [
                tesseract_bin,
                "stdin" if isinstance(source, bytes) else source,
                "stdout",
                "--psm",
                str(psm),
                "-l",
                "eng",
                "-c",
                "tessedit_char_whitelist=0123456789",
            ],
            input=source if isinstance(source, bytes) else None,
            env=env,
            capture_output=True,
            check=True,
        )
        return re.sub(r"\D", "", result.stdout.decode(errors="replace"))

    with Image.open(image_path) as image:
        gray = image.convert("L")
        cleaned = gray.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
        cleaned = cleaned.resize((cleaned.width * 3, cleaned.height * 3))
        buffer = BytesIO()
        cleaned.save(buffer, format="PNG")

    digits = recognize(buffer.getvalue(), 7)
    if len(digits) == 4:
        return digits

    candidate = recognize(str(image_path), 7)
    if len(candidate) == 4:
        return candidate
    if len(candidate) > len(digits):
        digits = candidate

    with Image.open(image_path) as image:
        cleaned = image.convert("L").filter(ImageFilter.MedianFilter(3))
        cleaned = cleaned.resize((cleaned.width * 3, cleaned.height * 3))
        buffer = BytesIO()
        cleaned.save(buffer, format="PNG")

    for psm in (7, 8):
        candidate = recognize(buffer.getvalue(), psm)
        if len(candidate) == 4:
            return candidate
        if len(candidate) > len(digits):
            digits = candidate
    raise ValueError(f"Expected 4 digits; OCR read {digits!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image_path", nargs="?", help="PNG or JPG path; read from stdin if omitted")
    args = parser.parse_args()
    try:
        print(read_four_digits(args.image_path))
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else exc.stderr
        parser.exit(1, f"error: {stderr.strip() or exc}\n")
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
