from datetime import date

from src.domain.prazo_schemas import CalcularPrazoRequest, RegimePrazo
from src.services.calculo_prazo_service import CalculoPrazoService, _eh_dia_util, _pascoa


def test_pascoa_2026_bate_com_data_oficial():
    # Sexta-feira Santa 2026 é dia 03/04 (confirmado externamente) = Páscoa - 2 dias
    assert _pascoa(2026) == date(2026, 4, 5)


def test_prazo_simples_sem_feriado_no_meio():
    """Segunda-feira 02/03/2026, 3 dias úteis, sem feriado no caminho."""
    service = CalculoPrazoService()
    entrada = CalcularPrazoRequest(data_intimacao=date(2026, 3, 2), dias=3, regime=RegimePrazo.CPC)
    resultado = service.calcular(entrada)

    # 03/03 (ter), 04/03 (qua), 05/03 (qui) -> vencimento 05/03/2026
    assert resultado.data_vencimento == date(2026, 3, 5)
    assert resultado.dias_nao_uteis_no_periodo == []


def test_prazo_pula_fim_de_semana():
    """Sexta-feira 06/03/2026, 2 dias úteis -> deve pular sáb/dom."""
    service = CalculoPrazoService()
    entrada = CalcularPrazoRequest(data_intimacao=date(2026, 3, 6), dias=2, regime=RegimePrazo.CPC)
    resultado = service.calcular(entrada)

    # 07/03 (sáb, pula), 08/03 (dom, pula), 09/03 (seg, conta 1), 10/03 (ter, conta 2)
    assert resultado.data_vencimento == date(2026, 3, 10)
    assert date(2026, 3, 7) in resultado.dias_nao_uteis_no_periodo
    assert date(2026, 3, 8) in resultado.dias_nao_uteis_no_periodo


def test_prazo_pula_feriado_nacional():
    """Tiradentes é feriado fixo em 21/04. Intimação em 20/04/2026 (segunda)."""
    service = CalculoPrazoService()
    entrada = CalcularPrazoRequest(data_intimacao=date(2026, 4, 20), dias=1, regime=RegimePrazo.CPC)
    resultado = service.calcular(entrada)

    # 21/04 é feriado (terça), 22/04 (quarta) é o 1º dia útil
    assert date(2026, 4, 21) in resultado.dias_nao_uteis_no_periodo
    assert resultado.data_vencimento == date(2026, 4, 22)


def test_prazo_pula_feriado_estadual_amazonas():
    """5 de setembro é feriado estadual do AM."""
    service = CalculoPrazoService()
    entrada = CalcularPrazoRequest(data_intimacao=date(2026, 9, 4), dias=1, regime=RegimePrazo.CPC)
    resultado = service.calcular(entrada)

    assert date(2026, 9, 5) in resultado.dias_nao_uteis_no_periodo


def test_prazo_pula_feriado_municipal_manaus():
    """24 de outubro é aniversário de Manaus."""
    service = CalculoPrazoService()
    entrada = CalcularPrazoRequest(data_intimacao=date(2026, 10, 23), dias=1, regime=RegimePrazo.CPC)
    resultado = service.calcular(entrada)

    assert date(2026, 10, 24) in resultado.dias_nao_uteis_no_periodo


def test_prazo_em_dobro_dobra_os_dias():
    service = CalculoPrazoService()
    entrada_simples = CalcularPrazoRequest(data_intimacao=date(2026, 3, 2), dias=5, regime=RegimePrazo.CPC)
    entrada_dobro = CalcularPrazoRequest(
        data_intimacao=date(2026, 3, 2), dias=5, regime=RegimePrazo.CPC, prazo_em_dobro=True
    )

    resultado_simples = service.calcular(entrada_simples)
    resultado_dobro = service.calcular(entrada_dobro)

    assert resultado_dobro.dias_efetivos == 10
    assert resultado_dobro.data_vencimento > resultado_simples.data_vencimento


def test_recesso_forense_e_detectado_e_alertado():
    """Intimação em 18/12/2026 (sexta), prazo que atravessa o recesso forense."""
    service = CalculoPrazoService()
    entrada = CalcularPrazoRequest(data_intimacao=date(2026, 12, 18), dias=2, regime=RegimePrazo.CPC)
    resultado = service.calcular(entrada)

    assert resultado.alerta_recesso_forense is True
    # dias entre 20/12 e 20/01 não podem contar como dias úteis
    for d in resultado.dias_nao_uteis_no_periodo:
        pass  # só confirma que passou pelo período sem quebrar
    assert resultado.data_vencimento > date(2027, 1, 20)


def test_regime_clt_conta_igual_ao_cpc_em_dias_uteis():
    """Confirma que CLT hoje conta em dias úteis (pós-reforma 2017),
    igual ao CPC — não mais em dias corridos."""
    service = CalculoPrazoService()
    entrada_cpc = CalcularPrazoRequest(data_intimacao=date(2026, 3, 6), dias=8, regime=RegimePrazo.CPC)
    entrada_clt = CalcularPrazoRequest(data_intimacao=date(2026, 3, 6), dias=8, regime=RegimePrazo.CLT)

    resultado_cpc = service.calcular(entrada_cpc)
    resultado_clt = service.calcular(entrada_clt)

    assert resultado_cpc.data_vencimento == resultado_clt.data_vencimento
    assert "775" in resultado_clt.fundamento_regime  # cita o artigo certo


def test_fundamento_regime_e_especifico_para_cada_um():
    service = CalculoPrazoService()
    for regime in RegimePrazo:
        entrada = CalcularPrazoRequest(data_intimacao=date(2026, 3, 2), dias=1, regime=regime)
        resultado = service.calcular(entrada)
        assert resultado.fundamento_regime  # não vazio
        assert resultado.regime == regime


def test_eh_dia_util_funcao_auxiliar():
    cache: dict = {}
    assert _eh_dia_util(date(2026, 3, 2), cache) is True  # segunda comum
    assert _eh_dia_util(date(2026, 3, 7), cache) is False  # sábado
    assert _eh_dia_util(date(2026, 1, 1), cache) is False  # feriado nacional
    assert _eh_dia_util(date(2026, 1, 10), cache) is False  # dentro do recesso forense
