"""
Schemas do módulo `classificar_caso`.

Aviso: os campos "classe_processual" e "assunto" aqui são uma classificação
descritiva (texto livre orientado pelo padrão TPU do CNJ), não os códigos
numéricos oficiais das Tabelas Processuais Unificadas — não temos acesso à
tabela oficial completa. Para peticionamento real, confirme o código exato
no sistema do tribunal (e-SAJ/PJe já sugerem os códigos ao digitar).
"""
from typing import List, Optional

from pydantic import BaseModel, Field


class ClassificarCasoRequest(BaseModel):
    fatos: dict = Field(default_factory=dict)  # normalmente a saída de extrair_fatos / resumo_atual


class RespostaClassificacao(BaseModel):
    area_direito: str
    classe_processual_sugerida: str  # descritiva, ex.: "Procedimento Comum Cível"
    assunto_sugerido: str  # descritivo, ex.: "Indenização por Dano Moral"
    template_id_sugerido: Optional[str] = None  # de templates_peticoes.json, se houver um adequado
    justificativa: str
    alternativas_consideradas: List[str] = Field(default_factory=list)
    aviso: str = (
        "Classificação descritiva orientada pelo padrão TPU do CNJ, não os "
        "códigos oficiais exatos — confirme o código correto no sistema do "
        "tribunal (e-SAJ/PJe) antes do protocolo."
    )
