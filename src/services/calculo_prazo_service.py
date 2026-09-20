"""
Módulo `calcular_prazos`: calcula prazos processuais em dias úteis.

Camada: services. 100% determinístico, sem IA — contagem de prazo é regra
matemática objetiva, não deixa espaço para "interpretação" da IA.

Base legal: desde a Reforma Trabalhista (Lei 13.467/2017), o art. 775 da
CLT passou a contar prazos em dias úteis, igual ao CPC (art. 219) — antes
disso a CLT contava em dias corridos. Hoje os 4 regimes suportados (CPC,
JEC, CLT, JEF) contam da mesma forma; o que muda é só o fundamento legal
citado na resposta.
"""
from datetime import date, timedelta
from typing import List

from ..domain.prazo_schemas import CalcularPrazoRequest, RegimePrazo, RespostaPrazo

_FUNDAMENTOS_POR_REGIME = {
    RegimePrazo.CPC: "CPC art. 219 — prazos em dias úteis no processo civil.",
    RegimePrazo.JEC: "Lei 9.099/1995 art. 12-A — prazos em dias úteis no Juizado Especial Cível.",
    RegimePrazo.CLT: "CLT art. 775 (redação da Lei 13.467/2017) — prazos em dias úteis no processo do trabalho.",
    RegimePrazo.JEF: "CPC art. 219, aplicado subsidiariamente ao Juizado Especial Federal (Lei 10.259/2001).",
}

# Feriados nacionais fixos (dia, mês)
_FERIADOS_NACIONAIS_FIXOS = [
    (1, 1),  # Confraternização Universal
    (4, 21),  # Tiradentes
    (5, 1),  # Dia do Trabalho
    (9, 7),  # Independência
    (10, 12),  # Nossa Senhora Aparecida
    (11, 2),  # Finados
    (11, 15),  # Proclamação da República
    (11, 20),  # Consciência Negra (nacional desde a Lei 14.759/2023)
    (12, 25),  # Natal
]

# Feriado estadual do Amazonas
_FERIADO_ESTADUAL_AM = (9, 5)  # Elevação do Amazonas à categoria de província

# Feriados municipais de Manaus
_FERIADOS_MUNICIPAIS_MANAUS = [
    (10, 24),  # Aniversário de Manaus
    (12, 8),  # Nossa Senhora da Conceição (padroeira)
]


def _pascoa(ano: int) -> date:
    """Calcula a data da Páscoa (domingo) para o ano informado, pelo
    algoritmo de Gauss/Meeus — necessário para os feriados móveis
    (Carnaval, Sexta-feira Santa, Corpus Christi)."""
    a = ano % 19
    b = ano // 100
    c = ano % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    L = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * L) // 451
    mes = (h + L - 7 * m + 114) // 31
    dia = ((h + L - 7 * m + 114) % 31) + 1
    return date(ano, mes, dia)


def _feriados_moveis(ano: int) -> List[date]:
    pascoa = _pascoa(ano)
    return [
        pascoa - timedelta(days=48),  # segunda-feira de Carnaval
        pascoa - timedelta(days=47),  # terça-feira de Carnaval
        pascoa - timedelta(days=2),  # Sexta-feira Santa
        pascoa + timedelta(days=60),  # Corpus Christi
    ]


def _feriados_do_ano(ano: int) -> set:
    feriados = set()
    for mes, dia in _FERIADOS_NACIONAIS_FIXOS:
        feriados.add(date(ano, mes, dia))
    feriados.add(date(ano, *_FERIADO_ESTADUAL_AM))
    for mes, dia in _FERIADOS_MUNICIPAIS_MANAUS:
        feriados.add(date(ano, mes, dia))
    feriados.update(_feriados_moveis(ano))
    return feriados


def _em_recesso_forense(d: date) -> bool:
    """Recesso forense: 20/12 a 20/01, inclusive (CPC art. 220 / CLT art. 775-A)."""
    if d.month == 12 and d.day >= 20:
        return True
    if d.month == 1 and d.day <= 20:
        return True
    return False


def _eh_dia_util(d: date, feriados_cache: dict) -> bool:
    if d.weekday() >= 5:  # sábado=5, domingo=6
        return False
    if _em_recesso_forense(d):
        return False
    if d.year not in feriados_cache:
        feriados_cache[d.year] = _feriados_do_ano(d.year)
    return d not in feriados_cache[d.year]


class CalculoPrazoService:
    def calcular(self, entrada: CalcularPrazoRequest) -> RespostaPrazo:
        dias_efetivos = entrada.dias * 2 if entrada.prazo_em_dobro else entrada.dias

        feriados_cache: dict = {}
        dias_nao_uteis: List[date] = []

        atual = entrada.data_intimacao
        contados = 0
        data_inicio_contagem = None
        houve_recesso = False

        while contados < dias_efetivos:
            atual = atual + timedelta(days=1)
            if _eh_dia_util(atual, feriados_cache):
                if data_inicio_contagem is None:
                    data_inicio_contagem = atual
                contados += 1
            else:
                dias_nao_uteis.append(atual)
                if _em_recesso_forense(atual):
                    houve_recesso = True

        return RespostaPrazo(
            data_intimacao=entrada.data_intimacao,
            dias_solicitados=entrada.dias,
            dias_efetivos=dias_efetivos,
            regime=entrada.regime,
            fundamento_regime=_FUNDAMENTOS_POR_REGIME[entrada.regime],
            data_inicio_contagem=data_inicio_contagem,
            data_vencimento=atual,
            dias_nao_uteis_no_periodo=dias_nao_uteis,
            alerta_recesso_forense=houve_recesso,
        )


# instância padrão usada pela aplicação
calculo_prazo_service = CalculoPrazoService()
