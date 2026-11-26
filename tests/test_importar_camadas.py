"""Testes da camada tipologia_v1."""
import json

import pandas as pd
import pytest

from build import importar_camadas as ic
from build.importar_base import ErroImportacao, importar


def doc(n, **extra):
    base = {
        "folder": "Pasta", "description": f"Descrição do documento {n}",
        "old_code": None, "new_code": f"AHU_ACL_CU_001, Cx. 1, D. {n}.",
        "reference_code": f"PT/AHU/CU/001/0001/{n:05d}",
        "document_id_and_date": f"{n}. 1700, Janeiro, 1, Lisboa", "ano_isolado": 1700,
        "extracted_typology": "OFÍCIO", "typology_status": True,
    }
    base.update(extra)
    return base


def escrever(tmp_path, docs):
    entrada = tmp_path / "entrada.json"
    entrada.write_text(json.dumps(docs, ensure_ascii=False), encoding="utf-8")
    return entrada


@pytest.fixture()
def corpus_com_base(tmp_path):
    """Base pronta, com casos de tipologia variados."""
    docs = [
        doc(1),
        doc(2, extracted_typology=" carta  ", typology_status=True),
        doc(3, extracted_typology="COSIJLTA", typology_status=False),
        doc(4, extracted_typology="UNKNOWN", typology_status=False),
        doc(5, extracted_typology="AUTO DE EXAME.", typology_status=False),
    ]
    entrada = escrever(tmp_path, docs)
    importar(entrada, tmp_path / "corpus", "t", esperado=len(docs))
    return entrada, tmp_path / "corpus", docs


# ---------------------------------------------------------------------------
# Normalização da tipologia
# ---------------------------------------------------------------------------

def test_normalizar_tipologia_so_mexe_na_forma():
    assert ic.normalizar_tipologia(" carta  régia ") == "CARTA RÉGIA"
    assert ic.normalizar_tipologia("AUTO DE EXAME.") == "AUTO DE EXAME"
    assert ic.normalizar_tipologia('"OFÍCIO"') == "OFÍCIO"
    assert ic.normalizar_tipologia(None) == ""


def test_chave_tipologia_ignora_acento_e_caixa():
    assert ic.chave_tipologia("Ofício") == ic.chave_tipologia("OFICIO") == "OFICIO"


def test_correcao_casa_com_acento_para_poder_corrigir_acento_trocado(tmp_path):
    """'OFICÍO' é erro de extração; 'OFÍCIO' é a forma certa. A tabela precisa distinguir as duas."""
    correcoes = ic.carregar_correcoes(tmp_path / "correcoes_tipologia.json")
    assert correcoes["OFICÍO"] == "OFÍCIO"
    assert "OFÍCIO" not in correcoes


def test_tabela_de_correcoes_e_criada_e_editavel(tmp_path):
    arq = tmp_path / "correcoes_tipologia.json"
    correcoes = ic.carregar_correcoes(arq)
    assert arq.exists()
    assert correcoes["COSIJLTA"] == "CONSULTA"
    assert "_LEIA-ME" not in correcoes

    arq.write_text(json.dumps({"_LEIA-ME": "x", "PRIMEIRA": "VIA"}), encoding="utf-8")
    assert ic.carregar_correcoes(arq) == {"PRIMEIRA": "VIA"}


def test_correcao_mal_formada_para_a_importacao(tmp_path):
    arq = tmp_path / "correcoes_tipologia.json"
    arq.write_text(json.dumps({"PRIMEIRA": ["VIA"]}), encoding="utf-8")
    with pytest.raises(ErroImportacao, match="string"):
        ic.carregar_correcoes(arq)


# ---------------------------------------------------------------------------
# Camada de tipologia
# ---------------------------------------------------------------------------

def test_camada_tipologia_uma_linha_por_doc_uid_na_ordem_da_base(corpus_com_base):
    entrada, corpus, docs = corpus_com_base
    ic.importar_camadas(entrada, corpus, "t")

    base = pd.read_parquet(corpus / "colecoes" / "t" / "documentos.parquet")
    df = pd.read_parquet(corpus / "camadas" / ic.CAMADA_TIPOLOGIA / "tipologia.parquet")
    assert len(df) == len(docs)
    assert df["doc_uid"].tolist() == base["doc_uid"].tolist()
    assert df["doc_uid"].is_unique


def test_camada_tipologia_normaliza_corrige_e_marca_desconhecida(corpus_com_base):
    entrada, corpus, _ = corpus_com_base
    ic.importar_camadas(entrada, corpus, "t")
    df = pd.read_parquet(corpus / "camadas" / ic.CAMADA_TIPOLOGIA / "tipologia.parquet")

    assert df.loc[1, "tipologia"] == "CARTA"
    assert df.loc[1, "tipologia_bruta"] == " carta  "

    # 'COSIJLTA' é erro de extração: a tabela de correções o conserta e a linha fica marcada.
    assert df.loc[2, "tipologia"] == "CONSULTA"
    assert bool(df.loc[2, "tipologia_corrigida"])

    # 'UNKNOWN' vira tipologia nula e nunca é canônica.
    assert pd.isna(df.loc[3, "tipologia"])
    assert not bool(df.loc[3, "typology_status"])

    # Tipologia fora do vocabulário canônico fica na camada, só com typology_status falso.
    assert df.loc[4, "tipologia"] == "AUTO DE EXAME"
    assert not bool(df.loc[4, "typology_status"])


def test_tipologia_corrigida_herda_o_status_canonico_dos_dados(tmp_path):
    """'OFICÍO' corrigido para 'OFÍCIO' deixa de ser 'a revisar', porque 'OFÍCIO' é canônica nos dados."""
    docs = [
        doc(1, extracted_typology="OFÍCIO", typology_status=True),
        doc(2, extracted_typology="OFICÍO", typology_status=False),
        doc(3, extracted_typology="AUTO DE EXAME", typology_status=False),
    ]
    entrada = escrever(tmp_path, docs)
    importar(entrada, tmp_path / "corpus", "t", esperado=len(docs))
    ic.importar_camadas(entrada, tmp_path / "corpus", "t")
    df = pd.read_parquet(tmp_path / "corpus" / "camadas" / ic.CAMADA_TIPOLOGIA / "tipologia.parquet")

    assert df["tipologia"].tolist() == ["OFÍCIO", "OFÍCIO", "AUTO DE EXAME"]
    assert df["typology_status"].tolist() == [True, True, False]
    assert df["tipologia_corrigida"].tolist() == [False, True, False]


def test_typology_status_invalido_para_a_importacao(tmp_path):
    entrada = escrever(tmp_path, [doc(1, typology_status="sim")])
    importar(entrada, tmp_path / "corpus", "t", esperado=1)
    with pytest.raises(ErroImportacao, match="typology_status"):
        ic.importar_camadas(entrada, tmp_path / "corpus", "t")


# ---------------------------------------------------------------------------
# Camada sociolinguística
# ---------------------------------------------------------------------------













# ---------------------------------------------------------------------------
# Proveniência: camada.json e manifesto
# ---------------------------------------------------------------------------









# ---------------------------------------------------------------------------
# Ligação com a base
# ---------------------------------------------------------------------------

def test_sem_a_base_a_mensagem_manda_importar_a_colecao(tmp_path):
    entrada = escrever(tmp_path, [doc(1)])
    with pytest.raises(ErroImportacao, match="Importe a coleção"):
        ic.importar_camadas(entrada, tmp_path / "corpus", "t")


def test_entrada_diferente_da_base_para_a_importacao(corpus_com_base):
    entrada, corpus, docs = corpus_com_base
    outra = escrever(corpus.parent, docs + [doc(99)])
    with pytest.raises(ErroImportacao, match="importar_base"):
        ic.importar_camadas(outra, corpus, "t")


