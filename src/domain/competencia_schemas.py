"""
Schemas do módulo `definir_competencia`.
"""
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class RamoJustica(str, Enum):
    ESTADUAL = "estadual"
    FEDERAL = "federal"
    TRABALHO = "trabalho"


class RitoCompetencia(str, Enum):
    JUIZADO_ESPECIAL = "juizado_especial"
    JUIZADO_ESPECIAL_FEDERAL = "juizado_especial_federal"
    COMUM = "comum"
    TRABALHISTA = "trabalhista"


class TipoReu(str, Enum):
    PESSOA_FISICA = "pessoa_fisica"
    PESSOA_JURIDICA_PRIVADA = "pessoa_juridica_privada"
    UNIAO = "uniao"
    AUTARQUIA_FEDERAL = "autarquia_federal"
    EMPRESA_PUBLICA_FEDERAL = "empresa_publica_federal"
    ESTADO = "estado"
    MUNICIPIO = "municipio"
    OUTRO = "outro"


class PartesCompetencia(BaseModel):
    autor_uf: Optional[str] = None
    autor_municipio: str
    reu_tipo: TipoReu
    reu_municipio: Optional[str] = None


class DefinirCompetenciaRequest(BaseModel):
    area: str  # ex.: "trabalhista", "consumidor", "familia", "previdenciario" etc.
    valor_estimado: Optional[float] = None
    salario_minimo_vigente: Optional[float] = None  # se omitido, usa o padrão do sistema
    partes: PartesCompetencia
    relacao_consumo: bool = False
    materia_complexa_ou_pericia: bool = False
    eh_acao_de_alimentos: bool = False
    municipio_imovel: Optional[str] = None  # para ações reais imobiliárias (CPC art. 47)
    municipio_prestacao_servico: Optional[str] = None  # para ações trabalhistas (CLT art. 651)


class RespostaCompetencia(BaseModel):
    ramo_justica: RamoJustica
    rito: RitoCompetencia
    foro_territorial: str
    fundamento_foro: str
    dispensa_advogado: bool
    teto_juizado_sm: Optional[float] = None
    dentro_do_teto: Optional[bool] = None
    alertas: List[str] = Field(default_factory=list)
    observacoes: str = (
        "Regras cobertas: domicílio do réu (regra geral), foro do consumidor "
        "(CDC art. 101, I), domicílio do alimentando (CPC art. 53, II), "
        "situação do imóvel (CPC art. 47), local da prestação de serviço "
        "(CLT art. 651), e teto dos Juizados (40/60 SM). NÃO cobre foro de "
        "eleição contratual nem competências especiais de leis extravagantes "
        "— confirme com o advogado responsável em casos fora do comum."
    )
