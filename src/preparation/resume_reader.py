"""Resume file reader — PDF/DOCX text extraction and resume directory listing."""

from pathlib import Path

import structlog

log = structlog.get_logger()


def extract_resume_text(filepath: str | Path) -> str:
    """Extract plain text from a resume file (.pdf or .docx).

    Args:
        filepath: Path to the resume file.

    Returns:
        Extracted text content as a string.

    Raises:
        ValueError: If the file extension is not .pdf or .docx.
        FileNotFoundError: If the file does not exist.
    """
    path = Path(filepath)
    ext = path.suffix.lower()

    if ext == ".pdf":
        import fitz  # PyMuPDF

        doc = fitz.open(str(path))
        pages = [page.get_text() for page in doc]
        doc.close()
        return "\n".join(pages)

    elif ext == ".docx":
        from docx import Document

        doc = Document(str(path))
        paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
        return "\n".join(paragraphs)

    else:
        raise ValueError(f"Unsupported resume file type: {ext!r}. Expected .pdf or .docx")


def list_resumes(resumes_dir: str | Path) -> list[dict]:
    """List all resumes in a directory with their extracted text.

    Args:
        resumes_dir: Path to the directory containing resume files.

    Returns:
        List of dicts with keys: name (filename), path (str), text (extracted content).
        Empty list if directory is empty or does not exist.
    """
    directory = Path(resumes_dir)
    if not directory.exists():
        log.warning("resumes_dir_missing", path=str(directory))
        return []

    resumes = []
    for filepath in sorted(directory.iterdir()):
        if filepath.suffix.lower() in (".pdf", ".docx"):
            try:
                text = extract_resume_text(filepath)
                resumes.append(
                    {
                        "name": filepath.name,
                        "path": str(filepath),
                        "text": text,
                    }
                )
            except Exception as exc:
                log.warning("resume_read_error", file=filepath.name, error=str(exc))

    log.info("resumes_listed", count=len(resumes), directory=str(directory))
    return resumes
