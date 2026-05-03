import os
import re
from pathlib import Path

# Dependencies are imported locally in the extraction functions to avoid caching issues.


class ExtractionError(Exception):
    """Raised when text cannot be extracted from a file."""
    pass


class UnsupportedFileTypeError(Exception):
    """Raised when the file type is not supported by the system."""
    pass


def clean_text(raw_text: str) -> str:
    """
    Cleans raw text for NLP processing.
    - removes non-printable characters
    - normalizes newlines
    - removes extra spaces
    - preserves paragraph structure
    """
    if not raw_text:
        return ""
        
    # Remove non-printable characters (keep basic whitespace and standard unicode)
    text = "".join(ch for ch in raw_text if ch.isprintable() or ch in ("\n", "\t", "\r"))
    
    # Normalize newlines
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"\r", "\n", text)
    
    # Remove excessive blank lines (reduce to max 2 consecutive newlines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    
    # Remove excessive spaces and tabs (more than 1 space to a single space)
    text = re.sub(r"[ \t]+", " ", text)
    
    # Strip leading/trailing whitespace on each line
    text = "\n".join(line.strip() for line in text.split("\n"))
    
    # Final pass to clean up empty lines caused by stripping
    text = re.sub(r"\n{3,}", "\n\n", text)
    
    return text.strip()


def extract_pdf(file_path: str) -> str:
    """Extracts text from a PDF file."""
    try:
        from pdfminer.high_level import extract_text as extract_pdf_text
    except ImportError:
        raise ExtractionError("pdfminer.six is not installed.")
        
    try:
        text = extract_pdf_text(file_path)
        return text
    except Exception as e:
        raise ExtractionError(f"Failed to read PDF {file_path}: {e}")


def extract_docx(file_path: str) -> str:
    """Extracts text from a DOCX file."""
    try:
        import docx
    except ImportError:
        raise ExtractionError("python-docx is not installed.")
        
    try:
        doc = docx.Document(file_path)
        paragraphs = [p.text for p in doc.paragraphs if p.text]
        return "\n".join(paragraphs)
    except Exception as e:
        raise ExtractionError(f"Failed to read DOCX {file_path}: {e}")


def extract_txt(file_path: str) -> str:
    """Extracts text from a TXT file."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        raise ExtractionError(f"Failed to read TXT {file_path}: {e}")


def extract_text(file_path: str) -> str:
    """
    Main entry point. Detects file type, extracts text, and cleans it.
    """
    path_obj = Path(file_path)
    if not path_obj.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
        
    if path_obj.stat().st_size == 0:
        raise ExtractionError(f"File is empty: {file_path}")

    ext = path_obj.suffix.lower()
    
    if ext == ".pdf":
        raw_text = extract_pdf(str(path_obj))
    elif ext == ".docx":
        raw_text = extract_docx(str(path_obj))
    elif ext == ".txt":
        raw_text = extract_txt(str(path_obj))
    else:
        raise UnsupportedFileTypeError(f"Unsupported file extension: {ext}. Expected .pdf, .docx, or .txt")

    cleaned_text = clean_text(raw_text)
    
    if not cleaned_text:
        raise ExtractionError(f"No text could be extracted from {file_path}")
        
    return cleaned_text
