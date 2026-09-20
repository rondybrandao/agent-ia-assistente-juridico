"""
Módulo `calcular_valor_causa`: soma os componentes do valor da causa (CPC
arts. 291-293), aplicando juros e multa quando informados, e somando
danos morais quando pedidos.

Camada: services. 100% determinístico, sem IA — mas com uma limitação
importante e deliberada: correção monetária por índice (INPC, IPCA, IGP-M,
SELIC, TR) NÃO é calculada aqui, porque isso exigiria a tabela oficial do
índice em cada mês do período, que este sistema não possui. Inventar um
fator de correção seria pior do que não calcular — por isso, quando um
componente pede correção por índice, ele é sinalizado como
"correcao_monetaria_pendente" e o valor sem essa correção é o que aparece
no total, com o alerta correspondente.

Juros e multa, ao contrário, são fórmulas matemáticas simples e objetivas
— por isso são calculados de verdade.
"""
from datetime import date
from typing import List

from ..domain.valor_causa_schemas import (
    CalcularValorCausaRequest,
    ComponenteValorCausa,
    IndiceCorrecao,
    ItemMemoriaCalculo,
    RespostaValorCausa,
)


class CalculoValorCausaService:
    def calcular(self, entrada: CalcularValorCausaRequest) -> RespostaValorCausa:
        data_calculo = entrada.data_calculo or date.today()

        itens: List[ItemMemoriaCalculo] = []
        subtotal = 0.0
        ha_correcao_pendente = False

        for componente in entrada.componentes:
            item = self._calcular_componente(componente, data_calculo)
            itens.append(item)
            subtotal += item.valor_atualizado
            if item.correcao_monetaria_pendente:
                ha_correcao_pendente = True

        danos_morais_incluidos = 0.0
        if entrada.danos_morais and entrada.danos_morais.pedido and entrada.danos_morais.valor_sugerido:
            danos_morais_incluidos = entrada.danos_morais.valor_sugerido

        valor_da_causa = subtotal + danos_morais_incluidos

        return RespostaValorCausa(
            itens=itens,
            subtotal_componentes=round(subtotal, 2),
            danos_morais_incluidos=round(danos_morais_incluidos, 2),
            valor_da_causa=round(valor_da_causa, 2),
            ha_correcao_monetaria_pendente=ha_correcao_pendente,
            data_calculo=data_calculo,
        )

    def _calcular_componente(
        self, componente: ComponenteValorCausa, data_calculo: date
    ) -> ItemMemoriaCalculo:
        meses_decorridos = None
        juros_aplicados = 0.0

        if componente.data_base is not None:
            dias_decorridos = (data_calculo - componente.data_base).days
            meses_decorridos = round(max(dias_decorridos, 0) / 30, 2)

            if componente.juros_mensais_pct:
                juros_aplicados = (
                    componente.valor_original * (componente.juros_mensais_pct / 100) * meses_decorridos
                )
        elif componente.juros_mensais_pct:
            # Tem taxa de juros mas não tem data_base para contar o
            # período — não dá pra calcular sem inventar quantos meses
            # se passaram, então não aplicamos juros nesse caso.
            juros_aplicados = 0.0

        multa_aplicada = 0.0
        if componente.multa_pct:
            multa_aplicada = componente.valor_original * (componente.multa_pct / 100)

        correcao_pendente = componente.indice_correcao != IndiceCorrecao.NENHUM
        valor_atualizado = componente.valor_original + juros_aplicados + multa_aplicada

        return ItemMemoriaCalculo(
            descricao=componente.descricao,
            valor_original=round(componente.valor_original, 2),
            meses_decorridos=meses_decorridos,
            juros_aplicados=round(juros_aplicados, 2),
            multa_aplicada=round(multa_aplicada, 2),
            correcao_monetaria_pendente=correcao_pendente,
            indice_correcao=componente.indice_correcao if correcao_pendente else None,
            valor_atualizado=round(valor_atualizado, 2),
        )


# instância padrão usada pela aplicação
calculo_valor_causa_service = CalculoValorCausaService()
