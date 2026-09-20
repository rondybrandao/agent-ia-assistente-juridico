"""
Schemas do módulo `gerar_pecas_acessorias`.

Reaproveita o mesmo formato de resposta de gerar_peticao (mesma classe
Peca/persistência), já que a lógica é a mesma: expandir um esqueleto fixo e
preencher com dados fornecidos. Só o schema de ENTRADA é mais simples,
porque cada peça acessória tem seu próprio conjunto de campos.
"""
from typing import Any, Dict

from pydantic import BaseModel, Field


class PecaAcessoriaRequest(BaseModel):
    template_id: str  # ex.: "procuracao_ad_judicia", "declaracao_hipossuficiencia"
    dados: Dict[str, Any] = Field(default_factory=dict)
