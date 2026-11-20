"""Testes da camada mape_en_v4 (tradução inglesa do MAPE)."""
import json

import pandas as pd
import pytest

from build import construir_app as ca
from build import importar_mape as im

COLUNAS = ["doc_id", "doc_source", "doc_box", "doc_number", "doc_type", "year", "month", "day",
           "reference_code", "doc_link", "Doc_Text_Port", im.COLUNA_EN]


def escrever_mape(pasta, linhas):
    arq = pasta / "mape.csv"
    with open(arq, "w", encoding="utf-8") as f:
        f.write("MetaData ,,,,,,,,,,,\n")
        pd.DataFrame(linhas, columns=COLUNAS).to_csv(f, index=False)
    return arq


def linha(doc_id, ref, pt, en, ano=1750):
    return [doc_id, "X", "Cx.1", "1", "CARTA", ano, None, None, ref, "", pt, en]


def test_chave_normaliza_o_codigo_do_mape():
    assert im.chave_referencia("PT/AHU/CU/001/0101/7581") == "PT/AHU/CU/001/0101/07581"
    assert im.chave_referencia(None, "AHU_ACL_CU_019, Cx. 1, D. 1.") == "PT/AHU/CU/019/0001/00001"
    assert im.chave_referencia(None, None) is None


def test_semelhanca_ignora_acento_pontuacao_e_colchetes():
    assert im.semelhanca("CARTA do [governador] ao rei.", "Carta do governador ao Rei") == 1.0
    assert im.semelhanca("CARTA do governador.", "REQUERIMENTO de Fulano sobre terras.") < 0.5
    assert im.semelhanca("", "x") == 0.0


def test_so_liga_a_traducao_quando_o_resumo_e_o_mesmo(tmp_path):
    base = pd.DataFrame({
        "doc_uid": ["t:1", "t:2", "t:3"],
        "reference_code": ["PT/AHU/CU/019/0001/00001", "PT/AHU/CU/019/0001/00002", None],
        "new_code": [None, None, "AHU_ACL_CU_019, Cx. 1, D. 3."],
        "description": ["CARTA do governador ao rei.", "OFÍCIO sobre gado.", "REQUERIMENTO de Fulano."],
    })
    base["chave"] = [im.chave_referencia(r, n) for r, n in zip(base["reference_code"], base["new_code"])]
    mape = im.ler_mape(escrever_mape(tmp_path, [
        linha(1, "PT/AHU/CU/019/0001/1", "CARTA do governador ao Rei.", "Letter from the governor."),
        linha(2, "PT/AHU/CU/019/0001/00002", "AVISO sobre outra coisa inteiramente.", "Notice."),
        linha(3, "PT/AHU/CU/019/0001/00003", "REQUERIMENTO de Fulano.", "Petition of Fulano."),
    ]))
    falha = im.ler_mape(escrever_mape(tmp_path, [linha(
        1, "PT/AHU/CU/019/0001/00001", "CARTA do governador ao rei.",
        "Exception occurred: HTTPSConnectionPool(host='x', port=443): Read timed out.")]))
    assert not im.parear(base, falha).set_index("doc_uid").loc["t:1", "ligado"]
    pares = im.parear(base, mape).set_index("doc_uid")
    assert pares.loc["t:1", "ligado"] and pares.loc["t:1", "resumo_en"] == "Letter from the governor."
    assert not pares.loc["t:2", "ligado"]            # mesmo código, outro texto: só para a auditoria
    assert pares.loc["t:3", "mape_doc_id"] == 3      # pareado pela cota do Resgate


def test_app_so_recebe_os_pares_ligados():
    docs = pd.DataFrame({"doc_uid": ["a", "b", "c"]})
    traducao = pd.DataFrame({"doc_uid": ["a", "b"], "resumo_en": ["A.", "B."],
                             "mape_doc_id": [1, 2], "ligado": [True, False]})
    out = ca.juntar_traducao(docs, traducao)
    assert out["resumo_en"].tolist()[0] == "A." and out["resumo_en"].isna().tolist() == [False, True, True]


def test_csv_sem_as_colunas_recusa(tmp_path):
    arq = tmp_path / "x.csv"
    arq.write_text("MetaData\nfoo,bar\n1,2\n", encoding="utf-8")
    with pytest.raises(im.ErroImportacao, match="colunas"):
        im.ler_mape(arq)


def test_camada_registra_fonte_credito_e_licenca():
    from tests.conftest import RAIZ
    arq = RAIZ / "corpus" / "camadas" / im.CAMADA_MAPE / "camada.json"
    if not arq.exists():
        pytest.skip("camada mape_en_v4 não construída")
    camada = json.loads(arq.read_text("utf-8"))
    assert camada["fonte"]["doi"] == "10.5281/zenodo.15481608"
    assert camada["fonte"]["licenca"] == "CC BY 4.0"
    assert len(camada["fonte"]["autores"]) == 5
