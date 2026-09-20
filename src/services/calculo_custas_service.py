"""
Módulo `calcular_custas`: calcula custas iniciais quando existe regra legal
estável o suficiente para confiar, e sinaliza como "não calculado" quando
depende de tabela específica de tribunal.

Camada: services. 100% determinístico, sem IA. Mesma filosofia do
calculo_valor_causa_service: melhor não calcular do que calcular errado.

O que É calculado com confiança:
- Juizados Especiais (estadual e federal), 1º grau: isenção de custas
  (Lei 9.099/1995 art. 54; mesma lógica se estende ao Juizado Federal),
  regra estável há décadas.
- Trabalhista: 2% sobre o valor da causa, mínimo R$ 10,64, máximo 4x o
  teto do RGPS (CLT art. 789) — percentual e piso fixados em lei desde
  2002, teto atualizado anualmente via configuração.

O que NÃO é calculado (calculo_disponivel=False):
- Vara comum estadual: cada Tribunal de Justiça tem sua própria tabela de
  custas, atualizada por lei ou provimento local.
- Vara federal comum: hoje regida pela Lei 9.289/1996 (1% do valor da
  causa, min/max em UFIR), mas há uma reforma legislativa em tramitação
  (PL 429/2024) que pode já ter mudado essa lógica — fixar um percentual
  aqui seria arriscado.

Elegibilidade à gratuidade da justiça (CPC art. 98) também NÃO é uma
resposta binária baseada em faixa de renda arbitrária — a lei prevê
presunção de veracidade para pessoa natural que declara hipossuficiência
(art. 99, §3º), sujeita a impugnação, não um corte numérico fixo.
"""
from typing import List, Optional, Tuple

from ..core.config import settings
from ..domain.custas_schemas import CalcularCustasRequest, RespostaCustas, RitoCustas

_PCT_CUSTAS_TRABALHISTA = 0.02
_MINIMO_CUSTAS_TRABALHISTA = 10.64


class CalculoCustasService:
    def calcular(self, entrada: CalcularCustasRequest) -> RespostaCustas:
        alertas: List[str] = []

        if entrada.rito in (RitoCustas.JUIZADO_ESPECIAL, RitoCustas.JUIZADO_FEDERAL):
            custas, fundamento = self._calcular_juizado(entrada.rito, alertas)
        elif entrada.rito == RitoCustas.TRABALHISTA:
            custas, fundamento = self._calcular_trabalhista(entrada.valor_causa, alertas)
        else:
            custas, fundamento = self._sem_calculo_disponivel(entrada.rito, alertas)

        elegibilidade = self._elegibilidade_gratuidade(entrada, alertas)

        return RespostaCustas(
            calculo_disponivel=custas is not None,
            custas_estimadas=custas,
            fundamento=fundamento,
            elegibilidade_gratuidade=elegibilidade,
            alertas=alertas,
        )

    def _calcular_juizado(self, rito: RitoCustas, alertas: List[str]) -> Tuple[Optional[float], str]:
        alertas.append(
            "Isenção vale para o 1º grau. Em caso de recurso, há custas e pode haver "
            "porte de remessa e retorno."
        )
        fundamento = (
            "Lei 9.099/1995 art. 54 — isenção de custas em 1º grau no Juizado Especial."
            if rito == RitoCustas.JUIZADO_ESPECIAL
            else "Lei 10.259/2001, mesma lógica de isenção em 1º grau do Juizado Especial Estadual."
        )
        return 0.0, fundamento

    def _calcular_trabalhista(self, valor_causa: float, alertas: List[str]) -> Tuple[Optional[float], str]:
        teto = 4 * settings.TETO_RGPS_VIGENTE
        custas = valor_causa * _PCT_CUSTAS_TRABALHISTA
        custas = max(custas, _MINIMO_CUSTAS_TRABALHISTA)
        if custas > teto:
            alertas.append(f"Valor calculado ultrapassa o teto legal (R$ {teto:.2f}) — aplicado o teto.")
            custas = teto
        fundamento = (
            f"CLT art. 789 — 2% sobre o valor da causa, mínimo R$ {_MINIMO_CUSTAS_TRABALHISTA:.2f}, "
            f"máximo 4x o teto do RGPS (hoje R$ {settings.TETO_RGPS_VIGENTE:.2f} = R$ {teto:.2f})."
        )
        return round(custas, 2), fundamento

    def _sem_calculo_disponivel(self, rito: RitoCustas, alertas: List[str]) -> Tuple[Optional[float], str]:
        if rito == RitoCustas.FEDERAL_COMUM:
            alertas.append(
                "A Justiça Federal tem reforma legislativa em tramitação (PL 429/2024) que pode "
                "já ter alterado a tabela de custas vigente (hoje regida pela Lei 9.289/1996) — "
                "confirme diretamente no tribunal antes de calcular manualmente."
            )
            fundamento = "Depende da tabela de custas vigente do TRF competente (Lei 9.289/1996 e normas locais)."
        else:
            alertas.append(
                "Confirme a tabela de custas vigente do tribunal estadual competente — varia por "
                "estado e é atualizada periodicamente."
            )
            fundamento = "Depende da tabela de custas vigente do Tribunal de Justiça competente."
        return None, fundamento

    def _elegibilidade_gratuidade(self, entrada: CalcularCustasRequest, alertas: List[str]) -> str:
        if not entrada.pede_gratuidade:
            return "Gratuidade não foi solicitada."

        texto = (
            "CPC art. 98 permite gratuidade a quem não pode arcar com custas sem prejuízo do "
            "próprio sustento. Para pessoa natural, o art. 99, §3º presume verdadeira a alegação "
            "de hipossuficiência feita na petição — não há um corte de renda fixado em lei; a "
            "presunção pode ser impugnada pela parte contrária ou pelo juízo, caso a caso."
        )
        if entrada.renda_mensal_autor is not None and entrada.renda_mensal_autor > 0:
            proporcao = entrada.valor_causa / entrada.renda_mensal_autor
            if proporcao < 1:
                alertas.append(
                    "Valor da causa é baixo em relação à renda informada — isso pode ser levado em "
                    "conta na avaliação da hipossuficiência, mas não impede o pedido por si só."
                )
        return texto


# instância padrão usada pela aplicação
calculo_custas_service = CalculoCustasService()
