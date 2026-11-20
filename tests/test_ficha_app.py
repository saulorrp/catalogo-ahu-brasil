"""Testes da ficha do documento e dos links para os acervos."""
from pathlib import Path

import pytest

from ahu import links
from ahu.dados import carregar_sem_cache
from ahu.ficha import marcar_termos, montar
from tests.conftest import APP_DADOS, tem_artefatos

RAIZ = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------------

def test_link_do_digitarq_usa_o_codigo_de_referencia():
    url = links.digitarq("PT/AHU/CU/021/0006/00390")
    assert url == ("https://digitarq.arquivos.pt/search?"
                   "query=PT%2FAHU%2FCU%2F021%2F0006%2F00390&isAdvancedSearch=false")


def test_sem_cota_nao_ha_link_do_digitarq():
    assert links.digitarq(None) is None
    assert links.digitarq("") is None
    assert links.digitarq("UNFORMATTED_CODE") is None   # a cota quebrada do catálogo


def test_link_do_resgate_e_o_portal():
    assert links.resgate("AHU_ACL_CU_021, Cx. 6, D. 390.") == links.RESGATE


# ---------------------------------------------------------------------------
# Destaque dos termos
# ---------------------------------------------------------------------------

def test_marcar_termos_destaca_a_palavra_do_texto_original():
    assert marcar_termos("CARTA sobre soldados", ["soldados"]) == "CARTA sobre **soldados**"


def test_marcar_termos_casa_grafia_antiga():
    """Quem buscou 'Melo' vê 'Mello' marcado."""
    assert marcar_termos("pedido de Manoel de Mello", ["melo"]) == "pedido de Manoel de **Mello**"


def test_marcar_termos_sem_termos_devolve_o_texto():
    assert marcar_termos("CARTA", []) == "CARTA"
    assert marcar_termos("", ["x"]) == ""


# ---------------------------------------------------------------------------
# Ficha
# ---------------------------------------------------------------------------

def test_ficha_tem_titulo_com_ano_tipologia_pessoa_e_pasta(corpus_busca):
    uid = corpus_busca.documentos["doc_uid"].iloc[0]
    f = montar(corpus_busca, uid)
    linha = corpus_busca.documentos.iloc[0]
    assert str(int(linha["ano_isolado"])) in f.titulo
    assert str(linha["tipologia"]) in f.titulo
    assert str(linha["folder"]) in f.titulo


def test_ficha_traz_cotas_e_links(corpus_busca):
    uid = corpus_busca.documentos["doc_uid"].iloc[4]   # o documento com cota conhecida
    f = montar(corpus_busca, uid)
    assert f.cotas["Código de referência"] == "PT/AHU/CU/021/0006/00390"
    assert f.cotas["Código atual"].startswith("AHU_ACL_CU_021")
    assert "digitarq" in f.links["digitarq"]
    assert f.links["resgate"].startswith("https://resgate.bn.gov.br")




def test_ficha_marca_tipologia_a_revisar(corpus_busca):
    fichas = [montar(corpus_busca, u) for u in corpus_busca.documentos["doc_uid"]]
    assert all(isinstance(f.tipologia_a_revisar, bool) for f in fichas)








def test_ficha_de_doc_uid_inexistente_avisa(corpus_busca):
    with pytest.raises(KeyError, match="doc_uid desconhecido"):
        montar(corpus_busca, "t:naoexiste")


# ---------------------------------------------------------------------------
# A1 sobre o corpus de verdade: todas as 167.344 fichas
# ---------------------------------------------------------------------------



@pytest.mark.skipif(not tem_artefatos, reason="app_dados/ ainda não construído")
def test_fichas_reais_tem_titulo_e_cota():
    dados = carregar_sem_cache(APP_DADOS)
    sem_titulo, sem_cota, sem_link = 0, 0, 0
    for uid, pasta in zip(dados.documentos["doc_uid"], dados.documentos["folder"]):
        f = montar(dados, uid)
        sem_titulo += not f.titulo
        sem_cota += not f.cotas
        if f.links.get("digitarq") is None and pasta not in ("Reino", "Códices"):
            sem_link += 1
    assert sem_titulo == 0 and sem_cota == 0
    # A Série Reino e os Códices não têm cota por série, caixa e documento, e por isso nenhum
    # link do DigitArq. Fora deles, sobram as cotas com erro de digitação no catálogo impresso.
    assert sem_link <= 200






# ---------------------------------------------------------------------------
# Navegar sem texto: um filtro sozinho vale como consulta
# ---------------------------------------------------------------------------

def test_sem_texto_a_resposta_e_o_corpus_filtrado(corpus_busca):
    from ahu.consulta import Consulta, executar
    from ahu.filtros import Filtros

    tudo = executar(corpus_busca, Consulta())
    assert tudo.total == len(corpus_busca.documentos)
    assert tudo.resultados[0].posicoes == {"corpus": 1}

    so_filtro = executar(corpus_busca, Consulta(filtros=Filtros(tipologias=["CARTA"])))
    assert 0 < so_filtro.total < tudo.total
    for r in so_filtro.resultados:
        assert corpus_busca.documentos.iloc[r.linha]["tipologia"] == "CARTA"




def test_ordenacao_por_ano_poe_sem_data_no_fim(corpus_busca):
    import pandas as pd

    from ahu.consulta import Consulta, executar

    anos = corpus_busca.documentos["ano_isolado"].copy()
    try:
        corpus_busca.documentos.loc[corpus_busca.documentos.index[2], "ano_isolado"] = None
        for ordem in ("ano_asc", "ano_desc"):
            r = executar(corpus_busca, Consulta(ordenacao=ordem))
            ultimo = corpus_busca.documentos.iloc[r.resultados[-1].linha]["ano_isolado"]
            assert pd.isna(ultimo), ordem
    finally:
        corpus_busca.documentos["ano_isolado"] = anos
