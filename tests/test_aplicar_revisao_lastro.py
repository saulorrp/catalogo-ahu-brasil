import pandas as pd

from build.aplicar_revisao_lastro import aplicar, nova_data


def _base():
    df = pd.DataFrame([
        {"doc_uid": "u:1", "description": "Portugal, ao secretário", "document_id_and_date": "5. 1745",
         "extracted_typology": None, "ano_isolado": 1745},
        {"doc_uid": "u:2", "description": "CARTA do governador", "document_id_and_date": "6. 1750, Maio, 14",
         "extracted_typology": "CARTA", "ano_isolado": 1750},
    ])
    df["ano_isolado"] = df["ano_isolado"].astype("Int64")
    return df


def test_escolha_a_troca_resumo_e_tipologia():
    d = [{"id_lastro": "X#1", "doc_uid": "u:1", "fonte_decisao": "modelo", "escolha_resumo": "A",
          "escolha_data": "B", "resumo": "OFÍCIO do vice-rei de Portugal, ao secretário", "data": "1745"}]
    nova, trocas, _ = aplicar(_base(), d)
    assert nova.at[0, "description"].startswith("OFÍCIO do vice-rei")
    assert nova.at[0, "extracted_typology"] == "OFÍCIO"
    assert nova.at[0, "document_id_and_date"] == "5. 1745"
    assert set(trocas["motivo"]) == {"revisar:modelo"}


def test_b_nenhum_e_pendente_nao_mudam():
    d = [{"doc_uid": "u:1", "fonte_decisao": "regra:fica_com_o_banco", "escolha_resumo": "B",
          "resumo": "OUTRO"},
         {"doc_uid": "u:2", "fonte_decisao": "modelo", "escolha_resumo": "nenhum", "resumo": "OUTRO"},
         {"doc_uid": "u:2", "fonte_decisao": "humano_pendente", "escolha_resumo": None}]
    nova, trocas, cont = aplicar(_base(), d)
    assert trocas.empty
    assert cont["humano_sem_resposta"] == 1


def test_humano_entra_depois_e_nao_repete():
    d = [{"doc_uid": "u:2", "fonte_decisao": "humano_pendente", "escolha_resumo": None}]
    humano = {"u:2": {"escolha_resumo": "C", "resumo": "CARTA do governador da Bahia", "escolha_data": "B"}}
    nova, trocas, _ = aplicar(_base(), d, humano)
    assert nova.at[1, "description"] == "CARTA do governador da Bahia"
    assert list(trocas["motivo"]) == ["revisar:humano"]
    _, trocas2, cont = aplicar(nova, d, humano, ja_feitos={"u:2"})
    assert trocas2.empty and cont["ja_aplicado"] == 1


def test_data_sem_ano_nao_substitui_data_com_ano():
    assert nova_data("6. 1750, Maio, 14, Bahia", "Maio, 14, Bahia") is None
    assert nova_data("6. [ant. 1750 REQUERIMENTO", "[ant. 1750]") == "6. [ant. 1750]"
    assert nova_data("6. 1750, Maio, 14", "1750, Maio, 14") is None
