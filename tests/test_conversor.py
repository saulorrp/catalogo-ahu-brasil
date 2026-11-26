"""Testes da aba Conversor (`ahu/conversor.py`).

Três níveis, e cada um com a sua prova: a formatação contra os 7.037 pares referência × Resgate
da base, a numeração igual contra os pares Castro e Almeida e Mendes Gouveia, e a concordância
contra casos escolhidos da base — inclusive os que **não** devem converter.
"""
from pathlib import Path

import pandas as pd
import pytest

from ahu import conversor as cv
from ahu.dados import carregar_sem_cache
from tests.conftest import APP_DADOS, tem_artefatos

# Erro de catálogo conhecido: `AHU_ACL_CU_0-21,Cx. 2, D. 90.` está na pasta Santa Catarina com a
# série 000-021. O conversor o trata como dado, sem regra própria.
# Erros de digitação dos catálogos (ex.: `017-00` por `017-01`): 11 documentos em 167 mil.
SERIES_COM_ERRO_NA_BASE = {"000", "000-01", "000-21", "017-00", "023-21"}
# A pasta da base escreve "Montividéu"; a cifra usa a grafia corrente.
GRAFIA_DA_PASTA = {"Montividéu": "Montevidéu"}


@pytest.fixture(scope="module")
def corpus_real():
    return carregar_sem_cache(APP_DADOS)


# ---------------------------------------------------------------------------
# Sem base: níveis 1 e 2
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("entrada, referencia, resgate", [
    ("AHU_ACL_CU_017, Cx. 69, D. 6420.", "PT/AHU/CU/017/0069/06420",
     "AHU_ACL_CU_017, Cx. 69, D. 6420."),
    ("PT/AHU/CU/019/0003/00230", "PT/AHU/CU/019/0003/00230", "AHU_ACL_CU_019, Cx. 3, D. 230."),
    ("AHU_ACL_CU_017Cx. 48, D. 4860.", "PT/AHU/CU/017/0048/04860",
     "AHU_ACL_CU_017, Cx. 48, D. 4860."),
    ("ahu acl cu 021 cx 6 d 390", "PT/AHU/CU/021/0006/00390", "AHU_ACL_CU_021, Cx. 6, D. 390."),
    ("AHU_ACL_CU_017, 8, D. 818.", "PT/AHU/CU/017/0008/00818", "AHU_ACL_CU_017, Cx. 8, D. 818."),
    # separadores digitados ou colados: contrabarra, barra, "Doc."/"Documento"
    ("AHU_ACL_CU_089, Cx. 10\\Doc. 955", "PT/AHU/CU/089/0010/00955",
     "AHU_ACL_CU_089, Cx. 10, D. 955."),
    ("AHU_ACL_CU_089/Cx. 10/D. 955", "PT/AHU/CU/089/0010/00955", "AHU_ACL_CU_089, Cx. 10, D. 955."),
    ("AHU_ACL_CU_019, Cx. 3, Documento 246", "PT/AHU/CU/019/0003/00246",
     "AHU_ACL_CU_019, Cx. 3, D. 246."),
    # uma série fora da cifra converte do mesmo jeito: a cota não precisa estar no corpus
    ("PT/AHU/CU/005/0135/10451", "PT/AHU/CU/005/0135/10451", "AHU_ACL_CU_005, Cx. 135, D. 10451."),
])
def test_nivel_1_e_so_formatacao(entrada, referencia, resgate):
    [c] = cv.converter(entrada)
    assert (c.referencia, c.resgate, c.nivel) == (referencia, resgate, 1)


@pytest.mark.parametrize("entrada, referencia, resgate", [
    ("PT/AHU/CU/017-001/0035/08229", "PT/AHU/CU/017-001/0035/08229",
     "AHU_ACL_CU_017-01, Cx. 35, D. 8229."),
    ("AHU_ACL_CU_017-01, Cx. 85, D. 19657-19674.", "PT/AHU/CU/017-001/0085/19657",
     "AHU_ACL_CU_017-01, Cx. 85, D. 19657-19674."),
])
def test_subserie_de_numeracao_igual_e_nivel_2(entrada, referencia, resgate):
    """Referência e Resgate continuam formatação; o nível 2 é o da cota antiga que vem junto."""
    [c] = cv.converter(entrada)
    assert (c.referencia, c.resgate, c.nivel) == (referencia, resgate, 2)
    assert c.antiga.startswith("AHU-Rio de Janeiro-Calmeida, cx. ")


def test_a_cifra_da_o_nome_e_a_serie_desconhecida_avisa():
    [rj] = cv.converter("PT/AHU/CU/017/0069/06420")
    assert rj.estado == "Rio de Janeiro" and not rj.avisos
    [ba] = cv.converter("PT/AHU/CU/005/0135/10451")
    assert ba.estado == "Bahia" and not ba.avisos
    [fora] = cv.converter("PT/AHU/CU/001/0001/00001")
    assert fora.estado is None and "não está na cifra" in fora.avisos[0]


def test_descrever_diz_o_que_foi_reconhecido_e_em_que_virou():
    [c] = cv.converter("AHU_ACL_CU_019, Cx. 3, D. 246")
    assert cv.descrever(c) == ("Reconhecido: **código atual** → código de referência · "
                               "Rio Grande do Sul (série 019) · por formatação")
    [mg] = cv.converter("AHU-São Paulo-MGouveia, cx. 2, doc. 126.")
    assert cv.descrever(mg).startswith(
        "Reconhecido: **código antigo** → código de referência e código atual")
    [nada] = cv.converter("lixo")
    assert cv.descrever(nada) == "Formato não reconhecido."


def test_serie_curta_e_completada_e_avisada():
    [c] = cv.converter("ahu acl cu 21 cx 6 d 390")
    assert c.referencia == "PT/AHU/CU/021/0006/00390"
    assert any("completada com zeros" in a for a in c.avisos)


def test_intervalo_avisa_que_a_referencia_guarda_so_o_primeiro():
    [c] = cv.converter("AHU_ACL_CU_017-01, Cx. 85, D. 19657-19674.")
    assert any("Intervalo de 18 documentos" in a for a in c.avisos)


@pytest.mark.parametrize("entrada, referencia, resgate", [
    ("AHU-São Paulo-MGouveia, cx. 2, doc. 126.", "PT/AHU/CU/023-001/0002/00126",
     "AHU_ACL_CU_023-01, Cx. 2, D. 126."),
    ("AHU-São Paulo, MGouveia, Cx. 3, doc. 317.", "PT/AHU/CU/023-001/0003/00317",
     "AHU_ACL_CU_023-01, Cx. 3, D. 317."),
    ("AHU-Rio de Janeiro-Calmeida, cx. 10, doc. 1817.", "PT/AHU/CU/017-001/0010/01817",
     "AHU_ACL_CU_017-01, Cx. 10, D. 1817."),
])
def test_nivel_2_numeracao_igual(entrada, referencia, resgate):
    [c] = cv.converter(entrada)
    assert (c.referencia, c.resgate, c.nivel) == (referencia, resgate, 2)


def test_nivel_2_tambem_no_sentido_inverso():
    [c] = cv.converter("AHU_ACL_CU_023-01, Cx. 2, D. 126.")
    assert c.antiga == "AHU-São Paulo-MGouveia, cx. 2, doc. 126." and c.nivel == 2


def test_cota_antiga_comum_sem_base_nao_converte():
    [c] = cv.converter("AHU-Rio de Janeiro, cx. 76, doc. 41.")
    assert not c.convertida and c.estado == "Rio de Janeiro"
    assert "depende da base" in c.avisos[0]


@pytest.mark.parametrize("entrada", ["AHU-Pará, n.v. 727", "cota inventada", "17", ""])
def test_formato_nao_reconhecido(entrada):
    [c] = cv.converter(entrada)
    assert not c.convertida and c.como == "sem conversão"


def test_cota_antiga_com_varias_cotas_vira_varias_linhas():
    cotas = cv.reconhecer_todas("AHU-Rio de Janeiro, cx. 279, doc. 48; cx. 280, doc. 111.")
    assert [(c.caixa, c.documento) for c in cotas] == [(279, 48), (280, 111)]
    assert {c.regiao for c in cotas} == {"Rio de Janeiro"}


def test_lista_ignora_grupos_notas_e_linhas_vazias():
    texto = "# Dia 1\nAHU_ACL_CU_017, Cx. 5, D. 487 | ver anexo\n\nPT/AHU/CU/019/0003/00230"
    conversoes = cv.converter_lista(texto)
    assert [c.referencia for c in conversoes] == ["PT/AHU/CU/017/0005/00487",
                                                   "PT/AHU/CU/019/0003/00230"]
    assert cv.para_lista_ahu(conversoes) == ("AHU_ACL_CU_017, Cx. 5, D. 487.\n"
                                            "AHU_ACL_CU_019, Cx. 3, D. 230.")


def test_tabelas_da_aba():
    t = cv.tabela(cv.converter_lista("PT/AHU/CU/017/0069/06420\nlixo"))
    assert list(t.columns) == ["Entrada", "Como", "Estado", "Código de referência",
                               "Código atual", "Código antigo", "DigitArq", "Avisos"]
    assert t["DigitArq"].iloc[0].startswith("https://digitarq.arquivos.pt/")
    assert t["DigitArq"].iloc[1] is None
    assert len(cv.tabela_da_cifra()) == len(cv.SERIES)


# ---------------------------------------------------------------------------
# Na base de verdade
# ---------------------------------------------------------------------------

def _validos(docs: pd.DataFrame) -> pd.DataFrame:
    return docs[(docs["reference_code"] != "UNFORMATTED_CODE") & docs["new_code"].notna()]


def _pares_digitarq() -> pd.DataFrame:
    """7.051 pares de cotas (referência, cota do Resgate, cota antiga) tirados do DigitArq.

    As cotas do catálogo foram geradas por este mesmo conversor, e conferi-las seria circular.
    Estes pares vêm de fora: foram copiados do DigitArq para uma base anterior do catálogo
    (Macrorregião Sul) e ficam congelados em `tests/fixtures/pares_digitarq.csv`."""
    return pd.read_csv(Path(__file__).parent / "fixtures" / "pares_digitarq.csv", dtype=str)


def test_formatacao_reproduz_todos_os_pares_da_base():
    """Resgate -> referência e referência -> Resgate -> referência, nos 7.050 pares.

    Eram 7.038; desde o build/cotas.py, os 12 documentos com `UNFORMATTED_CODE` ganham a
    referência pelo `new_code` e entram aqui."""
    pares = _validos(_pares_digitarq())
    assert len(pares) == 7050
    erradas = []
    for referencia, resgate in zip(pares["reference_code"], pares["new_code"]):
        ida = cv.para_referencia(cv.reconhecer(resgate))
        volta = cv.para_referencia(cv.reconhecer(cv.para_resgate(cv.reconhecer(referencia))))
        if ida != referencia or volta != referencia:
            erradas.append((referencia, resgate, ida, volta))
    assert not erradas, erradas[:5]


def test_nivel_2_reproduz_calmeida_e_mgouveia_da_base():
    docs = _pares_digitarq()
    antigas = docs[docs["old_code"].fillna("").str.contains("Calmeida|gouveia", case=False)]
    assert len(antigas) == 98
    for antiga, referencia in zip(antigas["old_code"], antigas["reference_code"]):
        c = cv.converter(antiga)[0]
        assert c.nivel == 2, antiga
        # O documento sem cota atual (`UNFORMATTED_CODE` e sem `new_code`) ganha uma aqui.
        if referencia != "UNFORMATTED_CODE":
            assert c.referencia == referencia, (antiga, c.referencia, referencia)


@pytest.mark.skipif(not tem_artefatos, reason="app_dados/ ainda não construído")
def test_a_cifra_confere_com_as_pastas_da_base(corpus_real):
    """Cada série da base está na cifra, e o nome da cifra é o da pasta.

    Falha quando uma importação nova trouxer uma série que a cifra não conhece: é a hora de
    acrescentá-la a `conversor.SERIES`.
    """
    docs = _validos(corpus_real.documentos)
    for resgate, pasta in zip(docs["new_code"], docs["folder"]):
        cota = cv.reconhecer(resgate)
        if cota is None or cota.codigo_serie is None:  # cota com erro de digitação
            continue
        codigo = cota.codigo_serie
        if codigo in SERIES_COM_ERRO_NA_BASE:
            continue
        assert codigo in cv.POR_CODIGO, (codigo, pasta)
        assert cv.POR_CODIGO[codigo].nome.split(",")[0] == GRAFIA_DA_PASTA.get(pasta, pasta), (
            codigo, pasta)


@pytest.mark.skipif(not tem_artefatos, reason="app_dados/ ainda não construído")
def test_nivel_3_concordancia_da_base(corpus_real):
    [sc] = cv.converter("AHU-Santa Catarina, cx. 13, doc. 46", corpus_real)
    assert (sc.referencia, sc.nivel, sc.estado) == ("PT/AHU/CU/021/0010/00543", 3,
                                                    "Santa Catarina")
    # grafia da região sem acento nem caixa, e `Colônia` casa `Colónia`
    [ncs] = cv.converter("ahu-nova colonia do sacramento, cx. 1, doc. 8", corpus_real)
    assert ncs.referencia == "PT/AHU/CU/012/0001/00007"


@pytest.mark.skipif(not tem_artefatos, reason="app_dados/ ainda não construído")
def test_nivel_3_uma_cota_antiga_pode_levar_a_varios_documentos(corpus_real):
    conversoes = cv.converter("AHU-Rio de Janeiro, cx. 76, doc. 41.", corpus_real)
    # 16 documentos do Rio de Janeiro com a mesma cota antiga.
    assert len(conversoes) == 16
    # Na ordem da base: a série 003 (Brasil Geral) vem antes da 017 (Rio de Janeiro).
    assert conversoes[0].referencia == "PT/AHU/CU/003/0019/01640"
    assert "PT/AHU/CU/017/0066/06200" in [c.referencia for c in conversoes]
    assert "PT/AHU/CU/017/0069/06420" in [c.referencia for c in conversoes]
    assert conversoes[0].avisos == ["1 de 16 documentos atuais com esta cota antiga."]


@pytest.mark.skipif(not tem_artefatos, reason="app_dados/ ainda não construído")
def test_nivel_3_le_cada_cota_de_um_campo_com_varias(corpus_real):
    """A segunda cota de `cx. 279, doc. 48; cx. 280, doc. 111` também acha o documento."""
    [c] = cv.converter("AHU-Rio de Janeiro, cx. 280, doc. 111", corpus_real)
    assert c.referencia == "PT/AHU/CU/017/0283/19907"


@pytest.mark.skipif(not tem_artefatos, reason="app_dados/ ainda não construído")
def test_cota_antiga_fora_da_base_nao_ganha_palpite(corpus_real):
    [c] = cv.converter("AHU-Rio de Janeiro, cx. 500, doc. 3", corpus_real)
    assert not c.convertida and c.como == "sem conversão"
    assert "não está na base" in c.avisos[0]


@pytest.mark.skipif(not tem_artefatos, reason="app_dados/ ainda não construído")
def test_cota_atual_da_base_ganha_a_cota_antiga_da_base(corpus_real):
    [c] = cv.converter("PT/AHU/CU/023/0027/01237", corpus_real)
    assert c.antiga == "AHU-São Paulo, cx. 26, doc. 8." and c.linha is not None
    assert any("tirado da base" in a for a in c.avisos)
    # o intervalo que a referência perdeu volta pela base
    [r] = cv.converter("PT/AHU/CU/017-001/0085/19657", corpus_real)
    assert r.resgate == "AHU_ACL_CU_017-01, Cx. 85, D. 19657-19674."






@pytest.mark.parametrize("entrada, referencia", [
    ("AHU_CU_011, Cx. 38, D. 3092.", "PT/AHU/CU/011/0038/03092"),
    ("AHU_ACL_CU_005, Cx. 33. D 2968.", "PT/AHU/CU/005/0033/02968"),
    ("AHU_CU_0005-01, Cx. 107, D. 20.836-20.840", "PT/AHU/CU/005-001/0107/20836"),
])
def test_variantes_dos_catalogos_impressos(entrada, referencia):
    [c] = cv.converter(entrada)
    assert c.referencia == referencia and not any("completada" in a for a in c.avisos)


def test_a_cifra_cobre_as_series_do_brasil():
    for codigo, nome in (("005-01", "Bahia, Castro e Almeida"), ("009", "Maranhão"),
                         ("015", "Pernambuco"), ("089", "Conselho Ultramarino")):
        assert cv.POR_CODIGO[codigo].nome == nome
