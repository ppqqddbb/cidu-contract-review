from pathlib import Path
import os
import shutil
import subprocess
import sys

from docx import Document
import fitz


def render_document_pages(path: str | Path, output_dir: str | Path, dpi: int = 144) -> dict:
    source = Path(path)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    pdf_path = source if source.suffix.lower() == ".pdf" else _docx_to_pdf(source, output)
    return {"pdf_path": str(pdf_path), "pages": _render_pdf(pdf_path, output, dpi)}


def _docx_to_pdf(source: Path, output_dir: Path) -> Path:
    pdf_path = output_dir / f"{source.stem}.pdf"
    try:
        return _docx_to_pdf_with_word(source, pdf_path)
    except Exception:
        pass
    try:
        return _docx_to_pdf_with_libreoffice(source, output_dir)
    except Exception:
        pass
    return _docx_to_text_pdf(source, output_dir)


def _docx_to_pdf_with_word(source: Path, pdf_path: Path) -> Path:
    word = None
    doc = None
    try:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        doc = word.Documents.Open(str(source.resolve()))
        _hide_review_markup(word, doc)
        doc.ExportAsFixedFormat(
            OutputFileName=str(pdf_path.resolve()),
            ExportFormat=17,
            OpenAfterExport=False,
            OptimizeFor=0,
            Range=0,
            Item=0,
            IncludeDocProps=True,
            KeepIRM=True,
            CreateBookmarks=0,
            DocStructureTags=True,
            BitmapMissingFonts=True,
            UseISO19005_1=False,
        )
    finally:
        if doc is not None:
            doc.Close(False)
        if word is not None:
            word.Quit()
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
    if not pdf_path.exists():
        raise RuntimeError("Microsoft Word did not generate PDF")
    return pdf_path


def _docx_to_pdf_with_libreoffice(source: Path, output_dir: Path) -> Path:
    soffice = _office_command()
    if not soffice:
        raise RuntimeError("LibreOffice executable not found")
    output_dir = output_dir.resolve()
    source = source.resolve()
    profile = output_dir / ".libreoffice-profile"
    profile.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            soffice,
            "--headless",
            f"-env:UserInstallation={profile.resolve().as_uri()}",
            "--convert-to",
            "pdf",
            "--outdir",
            str(output_dir),
            str(source),
        ],
        check=True,
        capture_output=True,
        timeout=180,
        cwd=str(Path(soffice).resolve().parent),
        env=_office_process_env(soffice),
        **_office_process_kwargs(),
    )
    pdf_path = output_dir / f"{source.stem}.pdf"
    if not pdf_path.exists():
        raise RuntimeError("LibreOffice did not generate PDF")
    return pdf_path


def _office_command() -> str | None:
    candidates: list[Path] = []
    configured = os.getenv("LIBREOFFICE_PATH", "").strip()
    if configured:
        candidates.append(Path(configured))
    executable_dir = Path(sys.executable).resolve().parent
    candidates.extend(
        [
            executable_dir / "libreoffice",
            executable_dir,
            Path(r"C:\Program Files\LibreOffice"),
            Path(r"C:\Program Files (x86)\LibreOffice"),
        ]
    )
    for command in (
        shutil.which("soffice.com"),
        shutil.which("soffice"),
        shutil.which("libreoffice"),
    ):
        if command:
            candidates.append(Path(command))
    seen: set[str] = set()
    for candidate in candidates:
        path = candidate
        if path.is_dir():
            path = path / "program" / "soffice.com"
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        if path.is_file():
            return str(path)
    return None


def _office_process_env(soffice: str) -> dict[str, str]:
    program_dir = str(Path(soffice).resolve().parent)
    path = os.environ.get("PATH", "")
    return {**os.environ, "PATH": f"{program_dir}{os.pathsep}{path}", "SAL_USE_VCLPLUGIN": "svp"}


def _office_process_kwargs() -> dict:
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return {"creationflags": subprocess.CREATE_NO_WINDOW, "startupinfo": startupinfo}


def _docx_to_text_pdf(source: Path, output_dir: Path) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    pdf_path = output_dir / f"{source.stem}.pdf"
    font_path = next(
        (
            path
            for path in (
                Path(r"C:\Windows\Fonts\msyh.ttc"),
                Path(r"C:\Windows\Fonts\simhei.ttf"),
                Path(r"C:\Windows\Fonts\simsun.ttc"),
                Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
                Path("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"),
                Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
            )
            if path.exists()
        ),
        None,
    )
    font = ImageFont.truetype(str(font_path), 25) if font_path else ImageFont.load_default()
    lines = _docx_preview_lines(source)
    image_paths: list[Path] = []
    for page_index, start in enumerate(range(0, max(1, len(lines)), 42), 1):
        image = Image.new("RGB", (1240, 1754), "white")
        draw = ImageDraw.Draw(image)
        y = 75
        for line in lines[start : start + 42]:
            draw.text((80, y), line, fill="#172033", font=font)
            y += 38
        image_path = output_dir / f"{source.stem}_preview_{page_index}.png"
        image.save(image_path)
        image_paths.append(image_path)

    pdf = fitz.open()
    try:
        for image_path in image_paths:
            image_doc = fitz.open(str(image_path))
            try:
                converted = fitz.open("pdf", image_doc.convert_to_pdf())
                try:
                    pdf.insert_pdf(converted)
                finally:
                    converted.close()
            finally:
                image_doc.close()
        if len(pdf) == 0:
            pdf.new_page(width=595, height=842)
        pdf.save(str(pdf_path))
    finally:
        pdf.close()
    return pdf_path


def _docx_preview_lines(source: Path) -> list[str]:
    document = Document(str(source))
    values: list[str] = []
    for paragraph in document.paragraphs:
        values.append(paragraph.text.strip())
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                values.append(" | ".join(cells))
    lines: list[str] = []
    for value in values or [""]:
        if not value:
            lines.append("")
            continue
        lines.extend(value[index : index + 35] for index in range(0, len(value), 35))
    return lines or [""]


def _hide_review_markup(word, doc) -> None:
    try:
        word.Options.PrintRevisions = False
    except Exception:
        pass
    try:
        word.ActiveWindow.View.RevisionsView = 0
    except Exception:
        pass
    try:
        word.ActiveWindow.View.ShowRevisionsAndComments = False
    except Exception:
        pass
    try:
        word.ActiveWindow.View.MarkupMode = 0
    except Exception:
        pass


def _render_pdf(pdf_path: Path, output_dir: Path, dpi: int) -> list[dict]:
    pages: list[dict] = []
    scale = dpi / 72
    doc = fitz.open(str(pdf_path))
    matrix = fitz.Matrix(scale, scale)
    for index, page in enumerate(doc, start=1):
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        image_path = output_dir / f"page-{index}.png"
        pixmap.save(str(image_path))
        pages.append(
            {
                "page_no": index,
                "image": image_path.name,
                "width": pixmap.width,
                "height": pixmap.height,
                "scale": scale,
            }
        )
    return pages

