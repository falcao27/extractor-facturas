"""Lectura del PDF: texto si es digital, imágenes PNG si es escaneado."""

import hashlib
import io
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

MIN_CHARS = 50
IMAGE_RESOLUTION = 150
MAX_PAGES = 10


class PdfInvalido(ValueError):
    pass


@dataclass
class PdfContent:
    texto: str
    imagenes: list[bytes] = field(default_factory=list)
    paginas: int = 0
    sha256: str = ""

    @property
    def escaneado(self) -> bool:
        return bool(self.imagenes)


def read_pdf(source: str | Path | bytes) -> PdfContent:
    """Extrae el texto de todas las páginas; si casi no hay texto, renderiza las páginas a PNG."""
    data = source if isinstance(source, bytes) else Path(source).read_bytes()
    sha256 = hashlib.sha256(data).hexdigest()
    try:
        pdf = pdfplumber.open(io.BytesIO(data))
    except Exception as exc:  # pdfminer lanza varios tipos según el daño del archivo
        raise PdfInvalido("O arquivo não é um PDF válido") from exc

    with pdf:
        if not pdf.pages:
            raise PdfInvalido("O PDF não tem páginas")
        pages = pdf.pages[:MAX_PAGES]
        texto = "\n\n".join((page.extract_text() or "") for page in pages).strip()
        if len(texto) >= MIN_CHARS:
            return PdfContent(texto=texto, paginas=len(pages), sha256=sha256)

        imagenes = []
        for page in pages:
            buffer = io.BytesIO()
            page.to_image(resolution=IMAGE_RESOLUTION).original.save(buffer, format="PNG")
            imagenes.append(buffer.getvalue())
        return PdfContent(texto=texto, imagenes=imagenes, paginas=len(pages), sha256=sha256)


def read_pdf_text(path: str | Path) -> str:
    """Atajo para depurar: `python -m app.pdf_reader factura.pdf`."""
    return read_pdf(path).texto


if __name__ == "__main__":
    import sys

    for arg in sys.argv[1:]:
        content = read_pdf(arg)
        print(f"== {arg} ({content.paginas} pág., escaneado={content.escaneado})")
        print(content.texto or "[sin texto: se enviará como imagen]")
