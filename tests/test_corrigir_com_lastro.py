import pandas as pd

from build.corrigir_com_lastro import corrigir, cortar_cota, especie, nova_data


def _base(**campos):
    linha = {"doc_uid": "ahu-brasil:1", "description": "", "document_id_and_date": "",
             "extracted_typology": None, "new_code": "AHU_CU_011, Cx. 1, D. 5.",
             "ano_isolado": pd.NA}
    linha.update(campos)
    df = pd.DataFrame([linha])
    df["ano_isolado"] = df["ano_isolado"].astype("Int64")
    return df


def _ouro(**campos):
    linha = {"doc_uid": "ahu-brasil:1", "fonte": "actd", "confirmacao": "dupla", "id_lastro": "X#1",
             "resumo": "", "data": "", "banco_resumo": None, "cota_texto": "AHU_CU_011, Cx. 1, D. 5",
             "anexo": None, "obs": None, "nota": None, "inventario": None, "remissao": None}
    linha.update(campos)
    return pd.DataFrame([linha])


def test_rodape_sai_do_resumo_e_vai_para_notas():
    base = _base(description="CARTA do governador. Nº de inventário no catálogo: 9084",
                 extracted_typology="CARTA")
    ouro = _ouro(resumo="CARTA do governador.", banco_resumo="sobra_no_fim",
                 inventario="Nº de inventário no catálogo: 9084", anexo="Anexo: 1 doc.")
    nova, trocas = corrigir(base, ouro)
    assert nova.at[0, "description"] == "CARTA do governador."
    assert nova.at[0, "notas_fonte"] == "Anexo: 1 doc. | Nº de inventário no catálogo: 9084"
    assert list(trocas["campo"]) == ["description"]


def test_comeco_que_foi_para_a_data_volta_ao_resumo():
    base = _base(description="Fernandes, sobre o contrabando.",
                 document_id_and_date="6. [ant. 1618, Julho, 24], Espírito Santo AUTO de diligência de")
    ouro = _ouro(resumo="AUTO de diligência de Fernandes, sobre o contrabando.",
                 data="[ant. 1618, Julho, 24], Espírito Santo",
                 banco_resumo="sem_inicio_que_foi_para_a_data")
    nova, trocas = corrigir(base, ouro)
    assert nova.at[0, "description"].startswith("AUTO de diligência")
    assert nova.at[0, "document_id_and_date"] == "6. [ant. 1618, Julho, 24], Espírito Santo"
    assert nova.at[0, "extracted_typology"] == "AUTO"
    assert nova.at[0, "ano_isolado"] == 1618
    assert set(trocas["campo"]) == {"description", "document_id_and_date", "extracted_typology",
                                    "ano_isolado"}


def test_ano_nao_sai_do_numero_do_documento():
    base = _base(description="Fernandes, sobre o contrabando.",
                 document_id_and_date="1447. [post. 1784, Maio, 2] OFÍCIO do")
    ouro = _ouro(resumo="OFÍCIO do governador Fernandes, sobre o contrabando.",
                 data="[post. 1784, Maio, 2]", banco_resumo="sem_inicio_que_foi_para_a_data")
    nova, _ = corrigir(base, ouro)
    assert nova.at[0, "document_id_and_date"] == "1447. [post. 1784, Maio, 2]"
    assert nova.at[0, "ano_isolado"] == 1784


def test_revisar_e_govbr_nao_mudam():
    base = _base(description="texto do banco")
    for ouro in (_ouro(resumo="OUTRO texto", confirmacao="revisar"),
                 _ouro(resumo="OUTRO texto", fonte="govbr")):
        nova, trocas = corrigir(base, ouro)
        assert nova.at[0, "description"] == "texto do banco"
        assert trocas.empty


def test_diferenca_so_de_acento_ou_pontuacao_nao_muda():
    base = _base(description="CARTA do governador - sobre o ouro")
    nova, trocas = corrigir(base, _ouro(resumo="CARTA do governador. Sobre o ouro"))
    assert trocas.empty


def test_cota_so_e_cortada_com_prova_do_lastro():
    suja = "AHU_CU_005-02, Cx. 13, D. 1553. 1553a 1654, Março, 17, Lisboa CONSULTA do Conselho"
    assert cortar_cota(suja) == "AHU_CU_005-02, Cx. 13, D. 1553."
    assert cortar_cota("AHU_CU_005-02, Cx. 13, D. 1553.") is None
    base = _base(new_code=suja)
    nova, _ = corrigir(base, _ouro(cota_texto="AHU_CU_005-02, Cx. 13, D. 1553."))
    assert nova.at[0, "new_code"] == "AHU_CU_005-02, Cx. 13, D. 1553."
    nova, _ = corrigir(base, _ouro(cota_texto="AHU_CU_005-02, Cx. 13, D. 1554."))
    assert nova.at[0, "new_code"] == suja


def test_data_so_muda_quando_o_corte_e_a_unica_mudanca():
    assert nova_data("9. 1700, Maio, 2 OFÍCIO do", "1700, Maio, 2", "sem_inicio_que_foi_para_a_data",
                     "") == "9. 1700, Maio, 2"
    assert nova_data("9. 1701, Maio, 2 OFÍCIO do", "1700, Maio, 2", "sem_inicio_que_foi_para_a_data",
                     "") is None
    assert nova_data("9. 1700, Maio, 2", "1700, Maio, 2", "igual", "") is None


def test_especie():
    assert especie("CARTA PATENTE de D. Rodrigo") == "CARTA PATENTE"
    assert especie("[OFÍCIO] do governador") == "OFÍCIO"
    assert especie("Consulta sobre a carta") is None
