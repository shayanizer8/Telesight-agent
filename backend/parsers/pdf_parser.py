import re

import pdfplumber


def parse_pdf(file_path: str) -> str:
    try:
        extracted_lines: list[str] = []

        with pdfplumber.open(file_path) as pdf_file:
            for page in pdf_file.pages:
                page_text = page.extract_text() or ""
                for line in page_text.splitlines():
                    cleaned_line = re.sub(r"\s+", " ", line).strip()
                    if cleaned_line:
                        extracted_lines.append(cleaned_line)

        return "\n".join(extracted_lines)
    except Exception as exc:
        raise RuntimeError(f"Failed to parse PDF file '{file_path}': {exc}") from exc