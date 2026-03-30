from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
import shutil
import subprocess
import tempfile

from PIL import Image, ImageDraw


@dataclass
class ReviewAssetsResult:
    backend: str
    pptx_path: str
    output_dir: str
    pdf_path: str | None = None
    slide_image_paths: list[str] = field(default_factory=list)
    contact_sheet_path: str | None = None
    deck_preview_path: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def has_full_slide_render(self) -> bool:
        return bool(self.slide_image_paths)


def review_assets_available() -> bool:
    return bool(_detect_backend())


def generate_powerpoint_review_assets(
    *,
    output_dir: str | Path,
    pptx_bytes: bytes | None = None,
    pptx_path: str | Path | None = None,
    deck_name: str = "neighbourhood_report",
    thumbnail_size: int = 2048,
    contact_sheet_columns: int = 3,
) -> ReviewAssetsResult:
    if pptx_bytes is None and pptx_path is None:
        raise ValueError("Provide either `pptx_bytes` or `pptx_path`.")

    backend = _detect_backend()
    output_root = Path(output_dir).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="ppt_review_") as temp_dir:
        temp_root = Path(temp_dir)
        if pptx_path is not None:
            source_path = Path(pptx_path).resolve()
            local_pptx_path = output_root / f"{deck_name}.pptx"
            if source_path != local_pptx_path:
                shutil.copy2(source_path, local_pptx_path)
        else:
            local_pptx_path = output_root / f"{deck_name}.pptx"
            local_pptx_path.write_bytes(pptx_bytes or b"")

        result = ReviewAssetsResult(
            backend=backend or "unavailable",
            pptx_path=str(local_pptx_path),
            output_dir=str(output_root),
        )

        if backend == "soffice":
            pdf_path = _convert_pptx_to_pdf(local_pptx_path, temp_root)
            if pdf_path is None:
                result.warnings.append("LibreOffice export did not produce a PDF.")
            else:
                rendered_dir = output_root / "rendered_slides"
                rendered_dir.mkdir(exist_ok=True)
                slide_paths = _render_pdf_to_pngs(pdf_path, rendered_dir, deck_name=deck_name)
                result.pdf_path = str(pdf_path)
                result.slide_image_paths = [str(path) for path in slide_paths]
                if slide_paths:
                    contact_sheet_path = output_root / f"{deck_name}_contact_sheet.png"
                    _build_contact_sheet(slide_paths, contact_sheet_path, columns=contact_sheet_columns)
                    result.contact_sheet_path = str(contact_sheet_path)
                    return result
                result.warnings.append("PDF rendering did not produce slide images.")

        if backend in {"qlmanage", "soffice"}:
            preview_path = _generate_quicklook_thumbnail(local_pptx_path, output_root, thumbnail_size=thumbnail_size)
            if preview_path is not None:
                result.deck_preview_path = str(preview_path)
            else:
                result.warnings.append("Quick Look thumbnail generation was unavailable.")
        else:
            result.warnings.append("No review backend is available on this machine.")

        return result


def _detect_backend() -> str | None:
    if shutil.which("soffice"):
        return "soffice"
    if shutil.which("qlmanage"):
        return "qlmanage"
    return None


def _convert_pptx_to_pdf(pptx_path: Path, temp_root: Path) -> Path | None:
    pdf_dir = temp_root / "pdf"
    pdf_dir.mkdir(exist_ok=True)
    command = [
        shutil.which("soffice") or "soffice",
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(pdf_dir),
        str(pptx_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        return None
    pdf_path = pdf_dir / f"{pptx_path.stem}.pdf"
    return pdf_path if pdf_path.exists() else None


def _render_pdf_to_pngs(pdf_path: Path, output_dir: Path, *, deck_name: str) -> list[Path]:
    prefix = output_dir / deck_name
    command = [
        shutil.which("pdftoppm") or "pdftoppm",
        "-png",
        "-r",
        "180",
        str(pdf_path),
        str(prefix),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        return []
    return sorted(output_dir.glob(f"{deck_name}-*.png"))


def _generate_quicklook_thumbnail(pptx_path: Path, output_dir: Path, *, thumbnail_size: int) -> Path | None:
    qlmanage = shutil.which("qlmanage")
    if qlmanage is None:
        return None
    command = [
        qlmanage,
        "-t",
        "-s",
        str(thumbnail_size),
        "-o",
        str(output_dir),
        str(pptx_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        return None
    expected = output_dir / f"{pptx_path.name}.png"
    if expected.exists():
        return expected
    matches = sorted(output_dir.glob(f"{pptx_path.name}*.png"))
    return matches[0] if matches else None


def _build_contact_sheet(slide_paths: list[Path], output_path: Path, *, columns: int) -> None:
    images = [Image.open(path).convert("RGB") for path in slide_paths]
    try:
        if not images:
            raise ValueError("No slide images were provided.")
        safe_columns = max(1, columns)
        thumb_width = max(image.width for image in images)
        thumb_height = max(image.height for image in images)
        rows = (len(images) + safe_columns - 1) // safe_columns
        margin = 24
        label_height = 28
        sheet = Image.new(
            "RGB",
            (
                safe_columns * thumb_width + (safe_columns + 1) * margin,
                rows * (thumb_height + label_height) + (rows + 1) * margin,
            ),
            (248, 248, 250),
        )
        draw = ImageDraw.Draw(sheet)
        for index, (path, image) in enumerate(zip(slide_paths, images, strict=False), start=1):
            row = (index - 1) // safe_columns
            column = (index - 1) % safe_columns
            left = margin + column * (thumb_width + margin)
            top = margin + row * (thumb_height + label_height + margin)
            canvas = Image.new("RGB", (thumb_width, thumb_height), (255, 255, 255))
            offset_x = (thumb_width - image.width) // 2
            offset_y = (thumb_height - image.height) // 2
            canvas.paste(image, (offset_x, offset_y))
            sheet.paste(canvas, (left, top))
            draw.rectangle((left, top, left + thumb_width, top + thumb_height), outline=(224, 214, 236), width=2)
            draw.text((left, top + thumb_height + 6), f"Slide {index}", fill=(33, 43, 50))
        sheet.save(output_path, format="PNG")
    finally:
        for image in images:
            image.close()
