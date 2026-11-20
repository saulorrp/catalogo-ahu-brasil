"""conftest.py — o corpus de mentira que os testes de busca, consulta e filtros compartilham.

Dez documentos inventados, com os casos que a busca precisa cobrir: grafia antiga
('Melo'/'Mello'), as três formas de cota e frase para a busca entre aspas. O índice semântico é
feito com o codificador falso de `test_construir_indice.py`, para não baixar o e5 nos testes.
"""
import json

import pytest

from ahu.dados import carregar_sem_cache
from build import construir_app as ca
from build import construir_indice as ci
from build import importar_camadas as ic
from build.importar_base import RAIZ, importar
from tests.test_construir_indice import Falso

APP_DADOS = RAIZ / "app_dados"
tem_artefatos = (APP_DADOS / "manifest.json").exists()


def documento(n, descricao=None, tipologia="CARTA"):
    """Um verbete mínimo do catálogo, com os campos da base."""
    return {
        "folder": "Pasta", "description": descricao or f"Descrição do documento {n}",
        "old_code": None, "new_code": f"AHU_ACL_CU_001, Cx. 1, D. {n}.",
        "reference_code": f"PT/AHU/CU/001/0001/{n:05d}",
        "document_id_and_date": f"{n}. 17{n:02d}, Janeiro, 1, Lisboa", "ano_isolado": 1700 + n,
        "extracted_typology": tipologia, "typology_status": True,
    }


def doc_busca(n, descricao, tipologia="CARTA", reference=None, new_code=None):
    d = documento(n, descricao, tipologia)
    if reference:
        d["reference_code"] = reference
    if new_code:
        d["new_code"] = new_code
    return d


@pytest.fixture(scope="module")
def corpus_busca(tmp_path_factory):
    """Dez documentos com casos de grafia, cota e frase, mais uma pessoa com variantes."""
    tmp_path = tmp_path_factory.mktemp("busca")
    docs = [
        doc_busca(1, "CARTA sobre a deserção de soldados da guarnição do presídio."),
        doc_busca(2, "OFÍCIO sobre desertores e a falta de mantimentos na fronteira.",
                  tipologia="OFÍCIO"),
        doc_busca(3, "REQUERIMENTO de Manuel de Melo, pedindo soldo atrasado.",
                  tipologia="REQUERIMENTO"),
        doc_busca(4, "CARTA de José Nunes sobre gado e cavalos da estância."),
        doc_busca(5, "CARTA sobre obras do porto e a ilha de Santa Catarina.",
                  reference="PT/AHU/CU/021/0006/00390",
                  new_code="AHU_ACL_CU_021, Cx. 6, D. 390."),
        doc_busca(6, "MAPA dos habitantes da vila, com soldados e moradores.", tipologia="MAPA"),
        doc_busca(7, "CARTA sobre a fuga de presos e a deserção da tropa paga."),
        doc_busca(8, "PARECER sobre o pedido de Manoel de Mello e Castro.", tipologia="PARECER"),
        # Subsérie (017-01 / 017-001) e intervalo de documentos: o caso que sumia da busca.
        doc_busca(9, "CONSULTA sobre a demarcação de limites no rio Uruguai.",
                  tipologia="CONSULTA",
                  reference="PT/AHU/CU/017-001/0057/13257",
                  new_code="AHU_CU_017-01, Cx. 57, D. 13257-13259."),
        doc_busca(10, "CARTA do governador ao vice-rei marquês do Lavradio sobre tropas."),
    ]
    entrada = tmp_path / "catalogo.json"
    entrada.write_text(json.dumps(docs, ensure_ascii=False), encoding="utf-8")

    corpus = tmp_path / "corpus"
    importar(entrada, corpus, "t", esperado=len(docs))
    ic.importar_camadas(entrada, corpus, "t")
    ci.construir_indice(corpus, None, "modelo-falso", Falso(), log=lambda *_: None)
    saida = tmp_path / "app_dados"
    ca.construir(corpus, saida)
    return carregar_sem_cache(saida)


@pytest.fixture(scope="module")
def encoder():
    return Falso()
