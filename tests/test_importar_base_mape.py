"""A base aberta (build/importar_base_mape.py): os verbetes do MAPE no formato comum do catálogo,
ligados pelo compat/ e prontos para o app. O CSV aqui é de mentira, com as colunas da versão 6."""
import json

import pandas as pd
import pytest

from ahu.dados import carregar_sem_cache
from ahu.links import do_documento
from build import construir_app as ca
from build import construir_indice as ci
from build import importar_base_mape as ibm
from tests.test_construir_indice import Falso

LINHAS = [
    # doc_id, reference_code, year, month, day, texto PT, texto EN
    (1, "PT/AHU/CU/021/0001/4", "1721-03", 3, 2,
     "OFÍCIO da Câmara da Ilha Fictícia sobre o porto.", "Letter from the council."),
    (2, "PT/AHU/CU/017-001/0001/00009.00019", "1760-01", None, None,
     "CARTA PATENTE do rei a um capitão fictício, com anexos.", "Royal patent."),
    (3, "PT/AHU/CU/005-002/0011/01335.A", "1790", None, None,
     "requerimento sem espécie em maiúsculas", "Request."),
    (4, "PT/AHU/CU/024/0001/00001", "1700", None, None, "CARTA de Angola.", "Letter."),
]


def csv_mape(tmp_path):
    df = pd.DataFrame(LINHAS, columns=["doc_id", "reference_code", "year", "month", "day",
                                       "doc_text_portuguese", "doc_text_english"])
    df["sender_name"] = "Remetente gerado por modelo"
    df["receiver_name"] = "Destinatário gerado por modelo"
    df["doc_type"] = "CARTA"
    arq = tmp_path / "mape.csv"
    df.to_csv(arq, index=False)
    return arq


def test_normaliza_o_codigo_e_guarda_o_intervalo():
    assert ibm.normalizar_codigo("PT/AHU/CU/021/1/4") == "PT/AHU/CU/021/0001/00004"
    assert ibm.normalizar_codigo("PT/AHU/CU/017-001/0001/9.19") == "PT/AHU/CU/017-001/0001/00009.00019"
    assert ibm.normalizar_codigo("PT/AHU/CU/005-002/0011/01335.A") == "PT/AHU/CU/005-002/0011/01335.A"
    assert ibm.normalizar_codigo("lixo") is None
    assert ibm.intervalo("PT/AHU/CU/017-001/0001/00009.00019") == (9, 19, False)
    assert ibm.intervalo("PT/AHU/CU/005-001/0023/04252.05254") == (4252, None, True)


def test_tipologia_e_data():
    assert ibm.tipologia("CARTA PATENTE do rei") == "CARTA PATENTE"
    assert ibm.tipologia("REQUERIMENTO de Manuel") == "REQUERIMENTO"
    assert ibm.tipologia("requerimento") is None
    assert ibm.data_texto("1821-10", 10.0, 17.0) == "1821, Outubro, 17"
    assert ibm.data_texto("1680-01", None, None) == "1680"


def test_monta_a_base_e_constroi_o_app(tmp_path):
    corpus = tmp_path / "corpus"
    contagem = ibm.importar(csv_mape(tmp_path), corpus)
    assert contagem["fora_da_cifra"] == 1  # série 024 (Angola)
    docs = pd.read_parquet(corpus / "colecoes" / ibm.COLECAO / "documentos.parquet")
    assert docs["doc_uid"].tolist() == ["mape-v6:1", "mape-v6:2", "mape-v6:3"]
    assert docs["new_code"].tolist()[:2] == ["AHU_ACL_CU_021, Cx. 1, D. 4.",
                                             "AHU_ACL_CU_017-01, Cx. 1, D. 9-19."]
    assert docs["folder"].tolist() == ["Santa Catarina", "Rio de Janeiro", "Bahia"]
    # nada gerado por modelo de linguagem entra na base
    assert not {"sender_name", "receiver_name", "doc_type"} & set(docs.columns)
    camada = json.loads((corpus / "colecoes" / ibm.COLECAO / "camada.json").read_text("utf-8"))
    assert camada["base"] == "mape"

    ci.construir_indice(corpus, None, "modelo-falso", Falso(), log=lambda *_: None)
    saida = tmp_path / "app_dados"
    ca.construir(corpus, saida)
    manifesto = json.loads((saida / "manifest.json").read_text("utf-8"))
    assert manifesto["base"] == "mape"
    dados = carregar_sem_cache(saida)
    d = dados.documentos.set_index("doc_uid")
    # links pelo compat/: o intervalo leva ao registro do DigitArq e ao quadro do primeiro número
    assert d.at["mape-v6:2", "reference_code"] == "PT/AHU/CU/017-001/0001/00009.00019"
    assert d.at["mape-v6:1", "resgate_docreader"] == "021_SC#37"
    assert do_documento(d.loc["mape-v6:1"])["resgate_direto"]
    # a cota antiga vem da concordância do compat/
    assert d.at["mape-v6:1", "old_code"] == "AHU-Santa Catarina, cx. 1, doc. 7"
    # a tradução é a do próprio MAPE
    assert d.at["mape-v6:1", "resumo_en"] == "Letter from the council."
    assert d.at["mape-v6:1", "resumo_en_fonte"] == "mape"


def test_exigir_v6_recusa_outro_arquivo(tmp_path):
    with pytest.raises(ibm.ErroImportacao):
        ibm.importar(csv_mape(tmp_path), tmp_path / "corpus", exigir_v6=True)
