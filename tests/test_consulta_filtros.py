"""Testes do objeto `Consulta`, da ida e volta para a URL e dos filtros."""
import numpy as np
import pytest

from ahu import busca
from ahu.consulta import (
    TAMANHO_PAGINA,
    VERSAO_URL,
    Consulta,
    ErroDeLink,
    executar,
)
from ahu.filtros import Filtros, opcoes

CONSULTAS_VARIADAS = [
    Consulta(),
    Consulta(texto="deserção de soldados"),
    Consulta(texto="Lavradio", modo="conceitual", rigor="alto", pagina=3),
    Consulta(texto='"obras do porto"', modo="exata", ordenacao="ano_desc"),
    Consulta(
        texto="soldados",
        filtros=Filtros(ano_de=1750, ano_ate=1800, sem_data=False, pastas=["Bahia", "Pará"],
                        tipologias=["CARTA", "OFÍCIO"], colecoes=["ahu-brasil"]),
        ordenacao="ano_asc", pagina=2,
    ),
]


# ---------------------------------------------------------------------------
# Ida e volta pela URL
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("consulta", CONSULTAS_VARIADAS, ids=lambda c: c.texto or "padrao")
def test_consulta_volta_igual_da_url(consulta):
    assert Consulta.de_url(consulta.para_url()) == consulta


@pytest.mark.parametrize("consulta", CONSULTAS_VARIADAS, ids=lambda c: c.texto or "padrao")
def test_consulta_volta_igual_do_dicionario(consulta):
    assert Consulta.de_dicionario(consulta.para_dicionario()) == consulta


def test_url_so_leva_o_que_nao_e_padrao():
    assert Consulta().para_url() == {"v": str(VERSAO_URL)}
    url = Consulta(texto="soldados").para_url()
    assert url == {"v": "2", "q": "soldados"}


def test_url_e_compacta_e_versionada():
    c = CONSULTAS_VARIADAS[-1]
    url = c.para_url()
    assert url["v"] == "2"
    assert all(len(k) <= 2 for k in url)          # chaves curtas
    assert url["ft"] == "CARTA|OFÍCIO"
    assert url["sd"] == "0"                       # booleanos como 0/1


def test_url_vazia_da_a_consulta_padrao():
    assert Consulta.de_url({}) == Consulta()
    assert Consulta.de_url(None) == Consulta()


def test_link_sem_versao_e_recusado():
    with pytest.raises(ErroDeLink, match="sem versão"):
        Consulta.de_url({"q": "soldados"})


def test_link_de_outra_versao_e_recusado():
    with pytest.raises(ErroDeLink, match="versão 99"):
        Consulta.de_url({"v": "99", "q": "soldados"})


def test_link_com_parametro_desconhecido_e_recusado():
    with pytest.raises(ErroDeLink, match="desconhecidos"):
        Consulta.de_url({"v": "2", "q": "x", "xyz": "1"})


def test_link_com_valor_invalido_e_recusado():
    with pytest.raises(ErroDeLink, match="Modo desconhecido"):
        Consulta.de_url({"v": "2", "m": "fuzzy"})
    with pytest.raises(ErroDeLink, match="número"):
        Consulta.de_url({"v": "2", "a1": "mil e setecentos"})
    with pytest.raises(ErroDeLink, match="0 ou 1"):
        Consulta.de_url({"v": "2", "sd": "talvez"})


def test_query_params_com_lista_funciona():
    """`st.query_params` devolve lista quando a chave repete."""
    assert Consulta.de_url({"v": ["2"], "q": ["soldados"]}) == Consulta(texto="soldados")


def test_consulta_invalida_avisa_na_criacao():
    with pytest.raises(ErroDeLink, match="Página"):
        Consulta(pagina=0)




# ---------------------------------------------------------------------------
# Filtros isolados
# ---------------------------------------------------------------------------

def test_filtros_vazios_nao_fazem_mascara(corpus_busca):
    assert Filtros().mascara(corpus_busca) is None


def quantos(dados, **kwargs) -> int:
    m = Filtros(**kwargs).mascara(dados)
    return int(m.sum()) if m is not None else len(dados.documentos)


def test_filtro_de_tipologia(corpus_busca):
    assert quantos(corpus_busca, tipologias=["CARTA"]) == 5
    assert quantos(corpus_busca, tipologias=["CARTA", "OFÍCIO"]) == 6
    assert quantos(corpus_busca, tipologias=["INEXISTENTE"]) == 0


def test_filtro_de_periodo_e_documentos_sem_data(corpus_busca):
    docs = corpus_busca.documentos
    anos = sorted(int(a) for a in docs["ano_isolado"].dropna())
    assert quantos(corpus_busca, ano_de=anos[0], ano_ate=anos[2]) == 3
    assert quantos(corpus_busca, ano_de=anos[-1]) == 1
    # Sem nenhum documento sem data, desligar a caixa não muda nada neste corpus.
    assert docs["ano_isolado"].isna().sum() == 0
    assert quantos(corpus_busca, sem_data=False) == len(docs)


def test_filtro_de_periodo_preserva_documento_sem_data_quando_pedido(corpus_busca):
    """A caixa 'incluir documentos sem data' salva quem não tem ano."""
    dados = corpus_busca
    anos = dados.documentos["ano_isolado"].copy()
    try:
        dados.documentos.loc[dados.documentos.index[0], "ano_isolado"] = None
        assert quantos(dados, ano_de=1800, ano_ate=1805, sem_data=True) >= 1
        com = quantos(dados, ano_de=1800, ano_ate=1805, sem_data=True)
        sem = quantos(dados, ano_de=1800, ano_ate=1805, sem_data=False)
        assert com == sem + 1
    finally:
        dados.documentos["ano_isolado"] = anos


















# ---------------------------------------------------------------------------
# Opções: saem dos dados
# ---------------------------------------------------------------------------

def test_opcoes_saem_dos_dados(corpus_busca):
    o = opcoes(corpus_busca)
    docs = corpus_busca.documentos
    assert o["colecoes"] == ["t"]
    assert o["mostrar_colecao"] is False          # oculto com uma coleção só
    assert set(o["pastas"]) == set(docs["folder"].dropna().unique())
    assert dict(o["tipologias"])["CARTA"] == 5
    assert o["ano_minimo"] == int(docs["ano_isolado"].min())
    assert o["documentos_sem_data"] == 0


def test_tipologias_vem_por_frequencia(corpus_busca):
    contagens = [n for _, n in opcoes(corpus_busca)["tipologias"]]
    assert contagens == sorted(contagens, reverse=True)










# ---------------------------------------------------------------------------
# Links antigos ainda abrem
# ---------------------------------------------------------------------------







def test_link_de_versao_futura_e_recusado():
    with pytest.raises(ErroDeLink, match="versão 9"):
        Consulta.de_url({"v": "9", "q": "gado"})




# ---------------------------------------------------------------------------
# Execução: busca com filtros e ordenação
# ---------------------------------------------------------------------------

def test_executar_aplica_os_filtros_na_busca(corpus_busca):
    sem = executar(corpus_busca, Consulta(texto="carta", modo="exata"))
    com = executar(corpus_busca, Consulta(texto="carta", modo="exata",
                                          filtros=Filtros(tipologias=["CARTA"])))
    assert 0 < com.total <= sem.total
    for r in com.resultados:
        assert corpus_busca.documentos.iloc[r.linha]["tipologia"] == "CARTA"


def test_filtro_tambem_vale_para_a_rota_de_cotas(corpus_busca):
    cota = "AHU_ACL_CU_021, Cx. 6, D. 390"
    livre = executar(corpus_busca, Consulta(texto=cota, modo="exata"))
    assert livre.total == 1
    bloqueado = executar(corpus_busca, Consulta(texto=cota, modo="exata",
                                                filtros=Filtros(tipologias=["MAPA"])))
    assert bloqueado.total == 0  # o filtro não é furado pela cota


def test_ordenacao_por_ano(corpus_busca):
    anos = corpus_busca.documentos["ano_isolado"]
    crescente = executar(corpus_busca, Consulta(texto="carta", modo="exata", ordenacao="ano_asc"))
    valores = [int(anos.iloc[r.linha]) for r in crescente.resultados]
    assert valores == sorted(valores)
    assert [r.posicao for r in crescente.resultados] == list(range(1, crescente.total + 1))

    decrescente = executar(corpus_busca, Consulta(texto="carta", modo="exata",
                                                  ordenacao="ano_desc"))
    assert [int(anos.iloc[r.linha]) for r in decrescente.resultados] == sorted(valores,
                                                                              reverse=True)


def test_pagina_de_25_e_o_padrao():
    assert TAMANHO_PAGINA == 25


# ---------------------------------------------------------------------------
# Aviso de consulta distante
# ---------------------------------------------------------------------------

def test_aviso_de_consulta_distante_e_so_aviso(corpus_busca, encoder):
    """Com as duas condições o aviso aparece, mas nada é cortado."""
    com = busca.buscar(corpus_busca, "xkq zzv plorb", encoder=encoder, cosseno_minimo=0.0,
                       limite_destaque=99.0)
    assert com.consulta_distante and busca.AVISO_DISTANTE in com.avisos
    sem = busca.buscar(corpus_busca, "xkq zzv plorb", encoder=encoder, cosseno_minimo=0.0,
                       limite_destaque=0.0)
    assert not sem.consulta_distante
    # O aviso não muda a lista: mesmos documentos, mesma ordem.
    assert [r.doc_uid for r in com.resultados] == [r.doc_uid for r in sem.resultados]
    assert [r.posicao for r in com.resultados] == [r.posicao for r in sem.resultados]


def test_aviso_exige_as_duas_condicoes(corpus_busca, encoder):
    """(a) nenhum termo no corpus E (b) topo sem destaque. Uma só não basta."""
    # 'soldados' está no corpus: condição (a) falha, nada de aviso nem com o limite altíssimo.
    com_lexico = busca.buscar(corpus_busca, "soldados", encoder=encoder, cosseno_minimo=0.0,
                              limite_destaque=99.0)
    assert com_lexico.sem_correspondencia_lexica is False
    assert not com_lexico.consulta_distante
    # 'xkq' não está: (a) vale, e aí o destaque decide.
    sem_lexico = busca.buscar(corpus_busca, "xkq", encoder=encoder, cosseno_minimo=0.0,
                              limite_destaque=99.0)
    assert sem_lexico.sem_correspondencia_lexica is True
    assert sem_lexico.consulta_distante


def test_termos_no_corpus_vale_em_qualquer_modo(corpus_busca):
    assert busca.termos_no_corpus(corpus_busca, ["soldados", "xkq"]) == ["soldados"]
    assert busca.termos_no_corpus(corpus_busca, ["xkq", "zzv"]) == []


def test_limite_do_destaque_e_provisorio_e_esta_nas_constantes():
    assert busca.LIMITE_DESTAQUE == 4.5
    assert "pouco relevantes" in busca.AVISO_DISTANTE
    assert not hasattr(busca, "PISO_AVISO_DISTANTE")  # o piso absoluto saiu


def test_busca_sem_semantico_nao_avisa(corpus_busca):
    r = busca.buscar(corpus_busca, "carta", modo="exata")
    assert r.cosseno_maximo is None and r.avisos == []


def test_destaque_do_topo_mede_o_quanto_o_melhor_se_separa():
    com_destaque = np.array([0.70] * 99 + [0.90], dtype=np.float32)
    sem_destaque = np.array([0.70, 0.701, 0.699] * 33 + [0.70], dtype=np.float32)
    assert busca.destaque_do_topo(com_destaque) > busca.destaque_do_topo(sem_destaque)
    assert busca.destaque_do_topo(np.array([0.5, 0.5, 0.5], dtype=np.float32)) == 0.0


# ---------------------------------------------------------------------------
# Sobre os artefatos de verdade (pulado se app_dados/ não existir)
# ---------------------------------------------------------------------------







def test_busca_ignora_duplicatas_marcadas():
    from types import SimpleNamespace

    import pandas as pd

    from ahu.consulta import sem_duplicatas

    docs = pd.DataFrame({"duplicata_de": [None, "antiga:a", None]})
    dados = SimpleNamespace(documentos=docs)
    assert sem_duplicatas(dados, None).tolist() == [True, False, True]
    assert sem_duplicatas(dados, np.array([False, True, True])).tolist() == [False, False, True]
    # sem a coluna (dados antigos), o filtro passa como veio
    assert sem_duplicatas(SimpleNamespace(documentos=pd.DataFrame({"x": [1]})), None) is None


def test_link_antigo_com_filtros_retirados_ainda_abre():
    """Um link de antes da reforma traz parâmetros que o catálogo não tem mais: eles caem, o resto vale."""
    c = Consulta.de_url({"v": "2", "q": "gado", "fu": "pes:1", "s1": "7", "fg": "Commoner",
                         "l": "x", "s": "42", "ft": "CARTA"})
    assert c == Consulta(texto="gado", filtros=Filtros(tipologias=["CARTA"]))
    v1 = Consulta.de_url({"v": "1", "q": "gado", "l": "lente"})
    assert v1 == Consulta(texto="gado")
