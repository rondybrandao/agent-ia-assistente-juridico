from src.domain.competencia_schemas import (
    DefinirCompetenciaRequest,
    PartesCompetencia,
    RamoJustica,
    RitoCompetencia,
    TipoReu,
)
from src.services.competencia_service import CompetenciaService

SM = 1621.00  # salário mínimo usado nos testes, mesmo valor do padrão do sistema


def _partes(**kwargs) -> PartesCompetencia:
    base = {"autor_municipio": "Manaus", "reu_tipo": TipoReu.PESSOA_JURIDICA_PRIVADA}
    base.update(kwargs)
    return PartesCompetencia(**base)


def test_caso_trabalhista_vai_para_justica_do_trabalho():
    service = CompetenciaService()
    entrada = DefinirCompetenciaRequest(area="trabalhista", partes=_partes())
    resultado = service.definir(entrada)
    assert resultado.ramo_justica == RamoJustica.TRABALHO
    assert resultado.rito == RitoCompetencia.TRABALHISTA
    assert resultado.dispensa_advogado is True  # jus postulandi sempre na Justiça do Trabalho


def test_reu_uniao_vai_para_justica_federal():
    service = CompetenciaService()
    entrada = DefinirCompetenciaRequest(
        area="civel", partes=_partes(reu_tipo=TipoReu.UNIAO)
    )
    resultado = service.definir(entrada)
    assert resultado.ramo_justica == RamoJustica.FEDERAL


def test_area_previdenciario_vai_para_justica_federal():
    service = CompetenciaService()
    entrada = DefinirCompetenciaRequest(area="previdenciario", partes=_partes())
    resultado = service.definir(entrada)
    assert resultado.ramo_justica == RamoJustica.FEDERAL


def test_caso_comum_vai_para_justica_estadual():
    service = CompetenciaService()
    entrada = DefinirCompetenciaRequest(area="civel", partes=_partes())
    resultado = service.definir(entrada)
    assert resultado.ramo_justica == RamoJustica.ESTADUAL


def test_valor_dentro_do_teto_estadual_usa_juizado_especial():
    service = CompetenciaService()
    entrada = DefinirCompetenciaRequest(area="consumidor", valor_estimado=30 * SM, partes=_partes())
    resultado = service.definir(entrada)
    assert resultado.rito == RitoCompetencia.JUIZADO_ESPECIAL
    assert resultado.dentro_do_teto is True


def test_valor_acima_do_teto_estadual_usa_vara_comum():
    service = CompetenciaService()
    entrada = DefinirCompetenciaRequest(area="consumidor", valor_estimado=50 * SM, partes=_partes())
    resultado = service.definir(entrada)
    assert resultado.rito == RitoCompetencia.COMUM
    assert resultado.dentro_do_teto is False
    assert any("teto do Juizado Especial Estadual" in a for a in resultado.alertas)


def test_valor_dentro_do_teto_federal_usa_juizado_especial_federal():
    service = CompetenciaService()
    entrada = DefinirCompetenciaRequest(
        area="previdenciario", valor_estimado=55 * SM, partes=_partes()
    )
    resultado = service.definir(entrada)
    assert resultado.rito == RitoCompetencia.JUIZADO_ESPECIAL_FEDERAL


def test_materia_complexa_forca_vara_comum_mesmo_dentro_do_teto():
    service = CompetenciaService()
    entrada = DefinirCompetenciaRequest(
        area="consumidor", valor_estimado=10 * SM, partes=_partes(), materia_complexa_ou_pericia=True
    )
    resultado = service.definir(entrada)
    assert resultado.rito == RitoCompetencia.COMUM
    assert any("complexa" in a.lower() for a in resultado.alertas)


def test_dispensa_advogado_ate_20_salarios_no_juizado_estadual():
    service = CompetenciaService()
    entrada = DefinirCompetenciaRequest(area="consumidor", valor_estimado=15 * SM, partes=_partes())
    resultado = service.definir(entrada)
    assert resultado.dispensa_advogado is True


def test_advogado_obrigatorio_acima_de_20_salarios_mesmo_no_juizado():
    service = CompetenciaService()
    entrada = DefinirCompetenciaRequest(area="consumidor", valor_estimado=25 * SM, partes=_partes())
    resultado = service.definir(entrada)
    assert resultado.rito == RitoCompetencia.JUIZADO_ESPECIAL  # ainda dentro do teto de 40 SM
    assert resultado.dispensa_advogado is False


def test_relacao_de_consumo_usa_foro_do_autor():
    service = CompetenciaService()
    entrada = DefinirCompetenciaRequest(
        area="consumidor",
        partes=_partes(autor_municipio="Manaus", reu_municipio="São Paulo"),
        relacao_consumo=True,
    )
    resultado = service.definir(entrada)
    assert resultado.foro_territorial == "Manaus"
    assert "CDC art. 101" in resultado.fundamento_foro


def test_acao_de_alimentos_usa_foro_do_alimentando():
    service = CompetenciaService()
    entrada = DefinirCompetenciaRequest(
        area="familia",
        partes=_partes(autor_municipio="Manacapuru", reu_municipio="Manaus"),
        eh_acao_de_alimentos=True,
    )
    resultado = service.definir(entrada)
    assert resultado.foro_territorial == "Manacapuru"
    assert "art. 53" in resultado.fundamento_foro


def test_regra_geral_usa_foro_do_reu():
    service = CompetenciaService()
    entrada = DefinirCompetenciaRequest(
        area="civel", partes=_partes(autor_municipio="Manaus", reu_municipio="Itacoatiara")
    )
    resultado = service.definir(entrada)
    assert resultado.foro_territorial == "Itacoatiara"
    assert "art. 46" in resultado.fundamento_foro


def test_acao_imobiliaria_usa_foro_do_imovel():
    service = CompetenciaService()
    entrada = DefinirCompetenciaRequest(
        area="imobiliario",
        partes=_partes(autor_municipio="Manaus", reu_municipio="Manaus"),
        municipio_imovel="Parintins",
    )
    resultado = service.definir(entrada)
    assert resultado.foro_territorial == "Parintins"
    assert "art. 47" in resultado.fundamento_foro


def test_foro_sem_dado_necessario_avisa_em_vez_de_inventar():
    service = CompetenciaService()
    entrada = DefinirCompetenciaRequest(area="civel", partes=_partes(reu_municipio=None))
    resultado = service.definir(entrada)
    assert "informe" in resultado.foro_territorial.lower()


def test_salario_minimo_customizado_e_respeitado():
    service = CompetenciaService()
    entrada = DefinirCompetenciaRequest(
        area="consumidor", valor_estimado=5000, salario_minimo_vigente=1000, partes=_partes()
    )
    resultado = service.definir(entrada)
    assert resultado.teto_juizado_sm == 40000  # 40 * 1000
