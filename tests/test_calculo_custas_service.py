from src.domain.custas_schemas import CalcularCustasRequest, RitoCustas
from src.services.calculo_custas_service import CalculoCustasService


def test_juizado_especial_estadual_isento_no_1_grau():
    service = CalculoCustasService()
    entrada = CalcularCustasRequest(tribunal="TJAM", rito=RitoCustas.JUIZADO_ESPECIAL, valor_causa=15000)
    resultado = service.calcular(entrada)

    assert resultado.calculo_disponivel is True
    assert resultado.custas_estimadas == 0.0
    assert "art. 54" in resultado.fundamento


def test_juizado_especial_federal_isento_no_1_grau():
    service = CalculoCustasService()
    entrada = CalcularCustasRequest(tribunal="TRF1", rito=RitoCustas.JUIZADO_FEDERAL, valor_causa=50000)
    resultado = service.calcular(entrada)

    assert resultado.custas_estimadas == 0.0


def test_trabalhista_calcula_2_por_cento():
    service = CalculoCustasService()
    entrada = CalcularCustasRequest(tribunal="TRT11", rito=RitoCustas.TRABALHISTA, valor_causa=10000)
    resultado = service.calcular(entrada)

    assert resultado.calculo_disponivel is True
    assert resultado.custas_estimadas == 200.0  # 2% de 10.000


def test_trabalhista_respeita_minimo_legal():
    """Valor da causa muito baixo: custas não podem ficar abaixo de R$ 10,64."""
    service = CalculoCustasService()
    entrada = CalcularCustasRequest(tribunal="TRT11", rito=RitoCustas.TRABALHISTA, valor_causa=100)
    resultado = service.calcular(entrada)

    # 2% de 100 = 2,00, mas o mínimo legal é 10,64
    assert resultado.custas_estimadas == 10.64


def test_trabalhista_respeita_teto_legal(monkeypatch):
    """Valor da causa altíssimo: custas não podem ultrapassar 4x o teto do RGPS."""
    from src.services import calculo_custas_service as modulo

    monkeypatch.setattr(modulo.settings, "TETO_RGPS_VIGENTE", 8475.55)
    service = CalculoCustasService()
    entrada = CalcularCustasRequest(tribunal="TRT11", rito=RitoCustas.TRABALHISTA, valor_causa=10_000_000)
    resultado = service.calcular(entrada)

    teto_esperado = round(4 * 8475.55, 2)
    assert resultado.custas_estimadas == teto_esperado
    assert any("teto legal" in a for a in resultado.alertas)


def test_vara_comum_estadual_nao_calcula_valor():
    """O ponto de segurança mais importante deste módulo: vara comum
    NUNCA recebe um valor fabricado de custas."""
    service = CalculoCustasService()
    entrada = CalcularCustasRequest(tribunal="TJAM", rito=RitoCustas.COMUM, valor_causa=50000)
    resultado = service.calcular(entrada)

    assert resultado.calculo_disponivel is False
    assert resultado.custas_estimadas is None


def test_vara_federal_comum_nao_calcula_valor_e_alerta_sobre_reforma():
    service = CalculoCustasService()
    entrada = CalcularCustasRequest(tribunal="TRF1", rito=RitoCustas.FEDERAL_COMUM, valor_causa=50000)
    resultado = service.calcular(entrada)

    assert resultado.calculo_disponivel is False
    assert resultado.custas_estimadas is None
    assert any("PL 429/2024" in a for a in resultado.alertas)


def test_gratuidade_nao_solicitada_retorna_texto_neutro():
    service = CalculoCustasService()
    entrada = CalcularCustasRequest(
        tribunal="TJAM", rito=RitoCustas.COMUM, valor_causa=50000, pede_gratuidade=False
    )
    resultado = service.calcular(entrada)

    assert resultado.elegibilidade_gratuidade == "Gratuidade não foi solicitada."


def test_gratuidade_solicitada_explica_presuncao_sem_corte_numerico():
    """Não deve haver nenhum número de 'renda mínima para ter direito' —
    a lei não define um corte fixo."""
    service = CalculoCustasService()
    entrada = CalcularCustasRequest(
        tribunal="TJAM", rito=RitoCustas.COMUM, valor_causa=50000, pede_gratuidade=True
    )
    resultado = service.calcular(entrada)

    assert "presume" in resultado.elegibilidade_gratuidade.lower()
    assert "art. 98" in resultado.elegibilidade_gratuidade
    assert "art. 99" in resultado.elegibilidade_gratuidade


def test_gratuidade_com_renda_baixa_gera_alerta_favoravel():
    service = CalculoCustasService()
    entrada = CalcularCustasRequest(
        tribunal="TJAM",
        rito=RitoCustas.COMUM,
        valor_causa=1000,
        pede_gratuidade=True,
        renda_mensal_autor=3000,
    )
    resultado = service.calcular(entrada)

    assert any("hipossuficiência" in a.lower() for a in resultado.alertas)
