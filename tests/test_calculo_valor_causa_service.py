from datetime import date

from src.domain.valor_causa_schemas import (
    CalcularValorCausaRequest,
    ComponenteValorCausa,
    DanosMoraisInput,
    IndiceCorrecao,
)
from src.services.calculo_valor_causa_service import CalculoValorCausaService


def test_componente_simples_sem_juros_multa_ou_correcao():
    service = CalculoValorCausaService()
    entrada = CalcularValorCausaRequest(
        componentes=[ComponenteValorCausa(descricao="Dívida principal", valor_original=1000.0)]
    )
    resultado = service.calcular(entrada)

    assert resultado.itens[0].valor_atualizado == 1000.0
    assert resultado.itens[0].correcao_monetaria_pendente is False
    assert resultado.subtotal_componentes == 1000.0
    assert resultado.valor_da_causa == 1000.0


def test_juros_mensais_calculados_corretamente():
    """1000 reais, 1% ao mês, exatos 2 meses (60 dias) -> 20 reais de juros."""
    service = CalculoValorCausaService()
    entrada = CalcularValorCausaRequest(
        componentes=[
            ComponenteValorCausa(
                descricao="Empréstimo",
                valor_original=1000.0,
                data_base=date(2026, 1, 1),
                juros_mensais_pct=1.0,
            )
        ],
        data_calculo=date(2026, 3, 2),  # 60 dias depois = 2.0 meses
    )
    resultado = service.calcular(entrada)

    assert resultado.itens[0].meses_decorridos == 2.0
    assert resultado.itens[0].juros_aplicados == 20.0
    assert resultado.itens[0].valor_atualizado == 1020.0


def test_multa_aplicada_uma_unica_vez():
    """1000 reais com multa de 10% -> 100 reais, aplicada uma vez só,
    independente da data."""
    service = CalculoValorCausaService()
    entrada = CalcularValorCausaRequest(
        componentes=[ComponenteValorCausa(descricao="Contrato", valor_original=1000.0, multa_pct=10.0)]
    )
    resultado = service.calcular(entrada)

    assert resultado.itens[0].multa_aplicada == 100.0
    assert resultado.itens[0].valor_atualizado == 1100.0


def test_correcao_monetaria_nunca_e_calculada_automaticamente():
    """O ponto de segurança mais importante deste módulo: pedir correção
    por índice NUNCA gera um valor fabricado — só a sinalização de
    pendência."""
    service = CalculoValorCausaService()
    entrada = CalcularValorCausaRequest(
        componentes=[
            ComponenteValorCausa(
                descricao="Valor a corrigir",
                valor_original=1000.0,
                data_base=date(2024, 1, 1),
                indice_correcao=IndiceCorrecao.IPCA,
            )
        ],
        data_calculo=date(2026, 1, 1),
    )
    resultado = service.calcular(entrada)

    assert resultado.itens[0].correcao_monetaria_pendente is True
    assert resultado.itens[0].indice_correcao == IndiceCorrecao.IPCA
    # o valor atualizado NÃO inclui nenhuma correção fabricada
    assert resultado.itens[0].valor_atualizado == 1000.0
    assert resultado.ha_correcao_monetaria_pendente is True


def test_juros_sem_data_base_nao_e_calculado():
    """Tem taxa de juros mas não tem data_base -> não dá pra saber quantos
    meses se passaram, então não inventa um número de meses."""
    service = CalculoValorCausaService()
    entrada = CalcularValorCausaRequest(
        componentes=[
            ComponenteValorCausa(descricao="Sem data base", valor_original=1000.0, juros_mensais_pct=2.0)
        ]
    )
    resultado = service.calcular(entrada)

    assert resultado.itens[0].juros_aplicados == 0.0
    assert resultado.itens[0].meses_decorridos is None


def test_danos_morais_incluidos_quando_pedido_true():
    service = CalculoValorCausaService()
    entrada = CalcularValorCausaRequest(
        componentes=[ComponenteValorCausa(descricao="Principal", valor_original=5000.0)],
        danos_morais=DanosMoraisInput(pedido=True, valor_sugerido=3000.0),
    )
    resultado = service.calcular(entrada)

    assert resultado.danos_morais_incluidos == 3000.0
    assert resultado.valor_da_causa == 8000.0


def test_danos_morais_nao_incluidos_quando_pedido_false():
    """Mesmo com valor_sugerido preenchido, se pedido=False não soma."""
    service = CalculoValorCausaService()
    entrada = CalcularValorCausaRequest(
        componentes=[ComponenteValorCausa(descricao="Principal", valor_original=5000.0)],
        danos_morais=DanosMoraisInput(pedido=False, valor_sugerido=3000.0),
    )
    resultado = service.calcular(entrada)

    assert resultado.danos_morais_incluidos == 0.0
    assert resultado.valor_da_causa == 5000.0


def test_multiplos_componentes_somam_no_subtotal():
    service = CalculoValorCausaService()
    entrada = CalcularValorCausaRequest(
        componentes=[
            ComponenteValorCausa(descricao="A", valor_original=1000.0),
            ComponenteValorCausa(descricao="B", valor_original=2500.0),
            ComponenteValorCausa(descricao="C", valor_original=500.0, multa_pct=10.0),
        ]
    )
    resultado = service.calcular(entrada)

    # A=1000, B=2500, C=500+50(multa)=550 -> subtotal = 4050
    assert resultado.subtotal_componentes == 4050.0
    assert len(resultado.itens) == 3


def test_data_calculo_padrao_e_hoje_quando_omitida():
    service = CalculoValorCausaService()
    entrada = CalcularValorCausaRequest(
        componentes=[ComponenteValorCausa(descricao="X", valor_original=100.0)]
    )
    resultado = service.calcular(entrada)

    assert resultado.data_calculo == date.today()


def test_juros_e_multa_aplicados_juntos_no_mesmo_componente():
    """1000 reais, 60 dias (2 meses) a 1% de juros ao mês + 2% de multa:
    juros = 20, multa = 20, total = 1040."""
    service = CalculoValorCausaService()
    entrada = CalcularValorCausaRequest(
        componentes=[
            ComponenteValorCausa(
                descricao="Combinado",
                valor_original=1000.0,
                data_base=date(2026, 1, 1),
                juros_mensais_pct=1.0,
                multa_pct=2.0,
            )
        ],
        data_calculo=date(2026, 3, 2),
    )
    resultado = service.calcular(entrada)

    assert resultado.itens[0].juros_aplicados == 20.0
    assert resultado.itens[0].multa_aplicada == 20.0
    assert resultado.itens[0].valor_atualizado == 1040.0
