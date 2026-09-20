"""
Entidades de domínio da triagem jurídica.

Camada: domain — define o "vocabulário" do negócio (o que é uma sessão, um
resumo de triagem, uma mensagem etc). Não depende de FastAPI, LLM, WhatsApp
ou banco de dados; qualquer uma dessas camadas depende deste módulo, nunca
o contrário.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from .estrategia_schemas import Estrategia
from .estrategia_schemas import Estrategia, RespostaEstrategias
from .fatos_schemas import RespostaExtracaoFatos


class Urgencia(str, Enum):
    BAIXA = "baixa"
    MEDIA = "media"
    ALTA = "alta"
    CRITICA = "critica"  # ex: prisão em flagrante, prazo processual iminente, risco físico


class StatusCaso(str, Enum):
    NOVO = "novo"  # ainda em triagem com o cliente, não encaminhado
    ENCAMINHADO = "encaminhado"  # triagem concluída, aguardando o advogado
    EM_ANDAMENTO = "em_andamento"  # advogado já está tratando o caso
    RESOLVIDO = "resolvido"
    ARQUIVADO = "arquivado"


class AreaDireito(str, Enum):
    TRABALHISTA = "trabalhista"
    CIVEL = "civel"
    FAMILIA = "familia"
    PENAL = "penal"
    CONSUMIDOR = "consumidor"
    TRIBUTARIO = "tributario"
    PREVIDENCIARIO = "previdenciario"
    EMPRESARIAL = "empresarial"
    IMOBILIARIO = "imobiliario"
    OUTRO = "outro"
    INDEFINIDO = "indefinido"


class Mensagem(BaseModel):
    remetente: str  # "usuario" | "assistente"
    texto: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class DadosContato(BaseModel):
    nome: Optional[str] = None
    telefone: str
    email: Optional[str] = None


class Anotacao(BaseModel):
    texto: str
    autor: str = "advogado"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class DadosPessoaisAutor(BaseModel):
    """
    Qualificação civil completa do autor — os mesmos campos exigidos pelos
    templates de petição (bloco qualificacao_pf). A triagem não deve se
    considerar concluída enquanto algum destes faltar (ver
    TriageService._deve_encaminhar).
    """
    nome: Optional[str] = None
    nacionalidade: Optional[str] = None
    estado_civil: Optional[str] = None
    profissao: Optional[str] = None
    cpf: Optional[str] = None
    rg: Optional[str] = None
    endereco_completo: Optional[str] = None
    cep: Optional[str] = None
    cidade: Optional[str] = None
    data_nascimento: Optional[str] = None

    def esta_completo(self) -> bool:
        campos = [
            self.nome,
            self.nacionalidade,
            self.estado_civil,
            self.profissao,
            self.cpf,
            self.rg,
            self.endereco_completo,
            self.cep,
            self.cidade,
            self.data_nascimento,
        ]
        return all(bool(c and c.strip()) for c in campos)

    def campos_faltando(self) -> List[str]:
        nomes_amigaveis = {
            "nome": "nome completo",
            "nacionalidade": "nacionalidade",
            "estado_civil": "estado civil",
            "profissao": "profissão",
            "cpf": "CPF",
            "rg": "RG",
            "endereco_completo": "endereço completo",
            "cep": "CEP",
            "cidade": "cidade",
            "data_nascimento": "data de nascimento",
        }
        return [
            amigavel
            for campo, amigavel in nomes_amigaveis.items()
            if not (getattr(self, campo) and getattr(self, campo).strip())
        ]


class ResumoTriagem(BaseModel):
    """
    Saída estruturada da triagem — o que efetivamente vai para o advogado.
    Nunca contém opinião jurídica, só fatos coletados na conversa.
    """
    area_direito: AreaDireito = AreaDireito.INDEFINIDO
    subtema: Optional[str] = None
    resumo_caso: Optional[str] = None
    urgencia: Urgencia = Urgencia.BAIXA
    motivo_urgencia: Optional[str] = None
    fatos_relevantes: List[str] = Field(default_factory=list)
    documentos_mencionados: List[str] = Field(default_factory=list)
    perguntas_em_aberto: List[str] = Field(default_factory=list)
    dados_pessoais_autor: DadosPessoaisAutor = Field(default_factory=DadosPessoaisAutor)
    pronto_para_advogado: bool = False


class SessaoConversa(BaseModel):
    telefone: str
    contato: DadosContato
    historico: List[Mensagem] = Field(default_factory=list)
    resumo_atual: ResumoTriagem = Field(default_factory=ResumoTriagem)
    consentimento_lgpd: bool = False
    encerrada: bool = False
    encaminhada_advogado: bool = False
    status_caso: StatusCaso = StatusCaso.NOVO
    anotacoes_advogado: List[Anotacao] = Field(default_factory=list)
    historico_pesquisa: List[Mensagem] = Field(default_factory=list)
    fatos_estruturados: Optional[RespostaExtracaoFatos] = None
    ultimas_estrategias: Optional[RespostaEstrategias] = None
    estrategia_escolhida: Optional[Estrategia] = None
    estrategia_escolhida: Optional[Estrategia] = None
    criada_em: datetime = Field(default_factory=datetime.utcnow)
    atualizada_em: datetime = Field(default_factory=datetime.utcnow)