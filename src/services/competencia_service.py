"""
Módulo `definir_competencia`: define ramo da Justiça, rito e foro
territorial. Deliberadamente 100% determinístico (sem IA) — são regras
processuais objetivas, então não há motivo para arriscar uma alucinação
aqui. Ver RespostaCompetencia.observacoes para o que este motor NÃO cobre.
"""
from ..core.config import settings
from ..domain.competencia_schemas import (
    DefinirCompetenciaRequest,
    RamoJustica,
    RespostaCompetencia,
    RitoCompetencia,
    TipoReu,
)

_TIPOS_REU_FEDERAIS = {
    TipoReu.UNIAO,
    TipoReu.AUTARQUIA_FEDERAL,
    TipoReu.EMPRESA_PUBLICA_FEDERAL,
}


class CompetenciaService:
    def definir(self, entrada: DefinirCompetenciaRequest) -> RespostaCompetencia:
        salario_minimo = entrada.salario_minimo_vigente or settings.SALARIO_MINIMO_VIGENTE
        alertas = []

        ramo = self._definir_ramo(entrada)
        rito, teto_sm, dentro_do_teto = self._definir_rito(entrada, ramo, salario_minimo, alertas)
        foro, fundamento = self._definir_foro(entrada, ramo)
        dispensa_advogado = self._definir_dispensa_advogado(entrada, ramo, rito, salario_minimo, alertas)

        return RespostaCompetencia(
            ramo_justica=ramo,
            rito=rito,
            foro_territorial=foro,
            fundamento_foro=fundamento,
            dispensa_advogado=dispensa_advogado,
            teto_juizado_sm=teto_sm,
            dentro_do_teto=dentro_do_teto,
            alertas=alertas,
        )

    def _definir_ramo(self, entrada: DefinirCompetenciaRequest) -> RamoJustica:
        if entrada.area.lower() == "trabalhista":
            return RamoJustica.TRABALHO
        if entrada.partes.reu_tipo in _TIPOS_REU_FEDERAIS or entrada.area.lower() == "previdenciario":
            return RamoJustica.FEDERAL
        return RamoJustica.ESTADUAL

    def _definir_rito(
        self,
        entrada: DefinirCompetenciaRequest,
        ramo: RamoJustica,
        salario_minimo: float,
        alertas: list,
    ):
        valor = entrada.valor_estimado

        if ramo == RamoJustica.TRABALHO:
            # Rito sumaríssimo (CLT art. 852-A) tem teto de 40 SM; acima
            # disso, rito ordinário. Aqui devolvemos RitoCompetencia.TRABALHISTA
            # nos dois casos (o template já trata a diferença internamente),
            # mas sinalizamos no alerta qual rito interno se aplica.
            teto = 40 * salario_minimo
            if valor is not None:
                if valor <= teto:
                    alertas.append(f"Valor dentro do teto do rito sumaríssimo ({teto:.2f}).")
                else:
                    alertas.append(f"Valor acima do teto do rito sumaríssimo ({teto:.2f}) — rito ordinário.")
            return RitoCompetencia.TRABALHISTA, teto, (valor <= teto if valor is not None else None)

        if ramo == RamoJustica.FEDERAL:
            teto = 60 * salario_minimo
            if entrada.materia_complexa_ou_pericia:
                alertas.append("Matéria complexa/pericial indicada — Juizado Federal pode não ser adequado mesmo dentro do teto.")
                return RitoCompetencia.COMUM, teto, (valor <= teto if valor is not None else None)
            if valor is not None and valor <= teto:
                return RitoCompetencia.JUIZADO_ESPECIAL_FEDERAL, teto, True
            if valor is not None:
                alertas.append(f"Valor ultrapassa o teto do Juizado Federal ({teto:.2f}) — vara federal comum.")
            return RitoCompetencia.COMUM, teto, (valor <= teto if valor is not None else None)

        # ESTADUAL
        teto = 40 * salario_minimo
        if entrada.materia_complexa_ou_pericia:
            alertas.append("Matéria complexa/pericial indicada — Juizado Especial pode não ser adequado mesmo dentro do teto.")
            return RitoCompetencia.COMUM, teto, (valor <= teto if valor is not None else None)
        if valor is not None and valor <= teto:
            return RitoCompetencia.JUIZADO_ESPECIAL, teto, True
        if valor is not None:
            alertas.append(
                f"Valor ultrapassa o teto do Juizado Especial Estadual ({teto:.2f}) — "
                "vara comum, ou Juizado com renúncia expressa ao excedente."
            )
        return RitoCompetencia.COMUM, teto, (valor <= teto if valor is not None else None)

    def _definir_foro(self, entrada: DefinirCompetenciaRequest, ramo: RamoJustica):
        if entrada.area.lower() == "imobiliario":
            if entrada.municipio_imovel:
                return (
                    entrada.municipio_imovel,
                    "CPC art. 47 — foro da situação do imóvel (ações reais imobiliárias).",
                )
            return (
                "(informe o município do imóvel)",
                "CPC art. 47 — foro da situação do imóvel; dado não informado.",
            )

        if entrada.eh_acao_de_alimentos:
            return (
                entrada.partes.autor_municipio,
                "CPC art. 53, II — foro do domicílio ou residência do alimentando.",
            )

        if entrada.relacao_consumo:
            return (
                entrada.partes.autor_municipio,
                "CDC art. 101, I — foro do domicílio do consumidor (autor).",
            )

        if ramo == RamoJustica.TRABALHO:
            municipio = entrada.municipio_prestacao_servico or entrada.partes.autor_municipio
            fundamento = "CLT art. 651 — foro do local da prestação dos serviços."
            if not entrada.municipio_prestacao_servico:
                fundamento += " (não informado; usando município do autor como aproximação)"
            return municipio, fundamento

        if ramo == RamoJustica.FEDERAL:
            return (
                entrada.partes.autor_municipio,
                "Lei 10.259/2001 art. 3º, §3º / CF art. 109, §2º — foro do domicílio do autor "
                "é permitido em ações contra a União e entes federais.",
            )

        # regra geral: domicílio do réu
        if entrada.partes.reu_municipio:
            return entrada.partes.reu_municipio, "CPC art. 46 — foro do domicílio do réu (regra geral)."
        return (
            "(informe o município do réu)",
            "CPC art. 46 — foro do domicílio do réu; dado não informado.",
        )

    def _definir_dispensa_advogado(
        self,
        entrada: DefinirCompetenciaRequest,
        ramo: RamoJustica,
        rito: RitoCompetencia,
        salario_minimo: float,
        alertas: list,
    ) -> bool:
        if ramo == RamoJustica.TRABALHO:
            # Jus postulandi é admitido na Justiça do Trabalho independente
            # de valor (CLT art. 791), embora pouco recomendável na prática.
            return True

        if rito == RitoCompetencia.JUIZADO_ESPECIAL and entrada.valor_estimado is not None:
            teto_dispensa = 20 * salario_minimo
            dispensa = entrada.valor_estimado <= teto_dispensa
            if not dispensa:
                alertas.append(
                    f"Valor acima de 20 salários mínimos ({teto_dispensa:.2f}) — "
                    "advogado obrigatório mesmo no Juizado Especial Estadual."
                )
            return dispensa

        return False


# instância padrão usada pela aplicação
competencia_service = CompetenciaService()
