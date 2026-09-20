"""
Módulo `exportar_documento`: exporta uma peça já gerada em .docx e/ou PDF
(PDF pesquisável, com texto real, não imagem), com numeração de páginas.

Camada: services. Depende só de bibliotecas padrão (python-docx, fpdf2) —
sem exigir LibreOffice/Word instalado na máquina, pra funcionar igual em
qualquer sistema operacional.
"""
import logging
from datetime import datetime
from io import BytesIO
from typing import Dict, List

from docx import Document
from docx.shared import Pt
from fpdf import FPDF

from ..domain.peticao_schemas import Peca
from ..repositories.peca_repository import peca_repository

logger = logging.getLogger(__name__)

_FORMATOS_VALIDOS = {"docx", "pdf"}


class _PdfComRodape(FPDF):
    """PDF com numeração de página no rodapé, como pedido pela spec."""

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Helvetica", size=8)
        self.cell(0, 10, f"Página {self.page_no()}/{{nb}}", align="C")


_SUBSTITUICOES_PDF = {
    "\u2014": "-",  # travessão —
    "\u2013": "-",  # meia-risca –
    "\u201c": '"',  # aspas curvas “
    "\u201d": '"',  # aspas curvas ”
    "\u2018": "'",  # aspas simples curvas ‘
    "\u2019": "'",  # aspas simples curvas ’
    "\u2026": "...",  # reticências unicode …
}


def _sanitizar_para_pdf(texto: str) -> str:
    """
    A fonte padrão do PDF (Helvetica core font) só suporta latin-1, que
    cobre acentuação em português normalmente, mas não travessão, aspas
    curvas etc. Sem isso, qualquer um desses caracteres quebra a geração.
    """
    for original, substituto in _SUBSTITUICOES_PDF.items():
        texto = texto.replace(original, substituto)
    return texto


class ExportacaoService:
    def gerar_docx(self, peca: Peca) -> bytes:
        doc = Document()

        titulo = doc.add_heading(peca.titulo, level=1)
        for run in titulo.runs:
            run.font.size = Pt(14)

        for paragrafo in peca.peca_texto.split("\n\n"):
            p = doc.add_paragraph(paragrafo.strip())
            p.style.font.size = Pt(11)

        rodape = doc.add_paragraph()
        rodape.add_run(
            f"\nGerado em {peca.criada_em:%d/%m/%Y %H:%M} — RASCUNHO, requer revisão de advogado."
        ).italic = True

        buffer = BytesIO()
        doc.save(buffer)
        return buffer.getvalue()

    def gerar_pdf(self, peca: Peca) -> bytes:
        pdf = _PdfComRodape()
        pdf.alias_nb_pages()
        pdf.add_page()
        pdf.set_font("Helvetica", size=11)

        pdf.set_font("Helvetica", "B", 14)
        pdf.multi_cell(0, 8, _sanitizar_para_pdf(peca.titulo))
        pdf.ln(4)

        pdf.set_font("Helvetica", size=11)
        for paragrafo in peca.peca_texto.split("\n\n"):
            pdf.multi_cell(0, 6, _sanitizar_para_pdf(paragrafo.strip()))
            pdf.ln(2)

        pdf.set_font("Helvetica", "I", 9)
        pdf.ln(4)
        pdf.multi_cell(
            0,
            5,
            _sanitizar_para_pdf(
                f"Gerado em {peca.criada_em:%d/%m/%Y %H:%M} — RASCUNHO, requer revisão de advogado."
            ),
        )

        saida = pdf.output()
        return bytes(saida)

    def exportar(self, peca_id: str, formatos: List[str]) -> Dict[str, bytes]:
        formatos_invalidos = set(formatos) - _FORMATOS_VALIDOS
        if formatos_invalidos:
            raise ValueError(f"Formato(s) inválido(s): {formatos_invalidos}. Use 'docx' e/ou 'pdf'.")

        peca = peca_repository.buscar(peca_id)
        if peca is None:
            raise ValueError(f"Peça '{peca_id}' não encontrada.")

        resultado: Dict[str, bytes] = {}
        if "docx" in formatos:
            resultado["docx"] = self.gerar_docx(peca)
        if "pdf" in formatos:
            resultado["pdf"] = self.gerar_pdf(peca)
        return resultado


# instância padrão usada pela aplicação
exportacao_service = ExportacaoService()
