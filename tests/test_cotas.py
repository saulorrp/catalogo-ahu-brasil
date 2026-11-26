"""Acertos de cota e de texto da construção (build/cotas.py) e o link do DigitArq que sai deles."""
import pandas as pd

import compat
from ahu import links
from ahu.ficha import marcar_sic
from build import cotas

INDICE = compat.IndiceDigitArq([
    "PT/AHU/CU/017-001/0016/03265.03267",
    "PT/AHU/CU/017-001/0016/03266",
    "PT/AHU/CU/017-001/0016/03426.03433",
    "PT/AHU/CU/022/0001/00067",
    "PT/AHU/CU/005/0054/04615",
])


def test_registro_do_digitarq():
    # o mesmo número de início vence o intervalo que o contém
    assert INDICE.achar("PT/AHU/CU/017-001/0016/03266") == "PT/AHU/CU/017-001/0016/03266"
    # documento dentro de um intervalo que começa antes
    assert INDICE.achar("PT/AHU/CU/017-001/0016/03429") == "PT/AHU/CU/017-001/0016/03426.03433"
    # caixa trocada entre o catálogo e o DigitArq
    assert INDICE.achar("PT/AHU/CU/022/0002/00067") == "PT/AHU/CU/022/0001/00067"
    assert INDICE.achar("PT/AHU/CU/017-001/0016/03500") is None
    assert INDICE.achar(None) is None


def test_ajustar_refaz_cotas_e_textos():
    base = pd.DataFrame({
        "new_code": ["AHU_CU_0005-01, Cx. 107, D. 20.836-20.840",
                     "AHU_CU_Reino, Cx. 133, pasta 10. INSTRUMENTO DE PESQUISA DOS DOCUMENTOS",
                     "AHU_CU_017-01, Cx. 16, D. 3429."],
        "reference_code": ["PT/AHU/CU/000-501/0107/20836", None, "PT/AHU/CU/017-001/0016/03429"],
        "description": ["Ordem da SãoSão Trindade.", "nau São São Sacramento", "sem erro"],
    })
    saida, contagem = cotas.ajustar(base, INDICE)
    saida, _ = compat.ligar(saida, compat.Tabelas(digitarq=INDICE))
    assert saida["reference_code"].tolist()[0] == "PT/AHU/CU/005-001/0107/20836"
    assert saida["new_code"].tolist()[1] == "AHU_CU_Reino, Cx. 133, pasta 10."
    # o resumo não se corrige: vem como a fonte o traz
    assert saida["description"].tolist() == base["description"].tolist()
    assert saida["referencia_digitarq"].tolist()[2] == "PT/AHU/CU/017-001/0016/03426.03433"
    assert contagem["referencia_refeita"] == 1
    assert contagem["new_code_sem_cabecalho"] == 1


def test_link_do_digitarq_por_registro_ou_caixa():
    com = {"reference_code": "PT/AHU/CU/017-001/0016/03429",
           "referencia_digitarq": "PT/AHU/CU/017-001/0016/03426.03433"}
    link = links.do_documento(com)
    assert "03426.03433" in link["digitarq"] and link["digitarq_rotulo"] == "Ficha no DigitArq"
    sem = {"reference_code": "PT/AHU/CU/081/0001/00010", "referencia_digitarq": None}
    link = links.do_documento(sem)
    assert link["digitarq"].endswith("query=PT%2FAHU%2FCU%2F081%2F0001&isAdvancedSearch=false")
    assert link["digitarq_rotulo"] == "Caixa no DigitArq"
    # base sem a coluna: busca pela referência, como antes
    assert "00010" in links.do_documento({"reference_code": "PT/AHU/CU/081/0001/00010"})["digitarq"]


def test_sic_marca_o_erro_da_fonte_sem_corrigir():
    marcado = marcar_sic("Ordem da SãoSão Trindade, Roque da Costa Barrreto, deTávora, D. João III")
    assert marcado.count("[sic]") == 3
    assert "SãoSão" in marcado and "Barrreto" in marcado and "III [sic]" not in marcado
    assert marcar_sic("carro de Lisboa, 1717") == "carro de Lisboa, 1717"


def test_ajustar_acertos_da_auditoria():
    base = pd.DataFrame({
        "doc_uid": ["antiga:a", "ahu-brasil:b", "ahu-brasil:c", "ahu-brasil:d", "ahu-brasil:e",
                    "ahu-brasil:f"],
        "colecao": ["antiga", "ahu-brasil", "ahu-brasil", "ahu-brasil", "ahu-brasil", "ahu-brasil"],
        "folder": ["Montividéu", "Nova Colônia do Sacramento", "Bahia", "Bahia", "Rio de Janeiro",
                   "Bahia"],
        "new_code": ["AHU_ACL_CU_012, Cx. 1, D. 36.", "AHU_CU_012, Cx. 1, D. .36.",
                     "AHU_CU_005-02, Cx. 12, D. 1399 - 1401.", "AHU_CU_005-02, Cx. 12, D. 1402.",
                     "AHU_CU_017-01, Cx. 14, D. 2950.", "AHU_CU_005-02, Cx. 15, D. 1784 - 1785."],
        "reference_code": [None] * 6,
        "document_id_and_date": ["36. 1722", "36. 1722", "1399. 1401", "1402. 1660", "2950. 1701",
                                 "1784. 1785 [ant. 1660, Novembro, 18]"],
        "ano_isolado": pd.array([1722, 1722, 1401, 1660, 1701, 1785], dtype="Int64"),
        "description": ["PROVISÃO (minuta) do rei.", "Provisão (minuta) do rei", "Carta.",
                        "Carta.", "Ofício.", "Consulta."],
    })
    saida, contagem = cotas.ajustar(base, None)
    # nada sai da base: o par repetido só é apontado por duplicatas()
    assert len(saida) == len(base)
    assert cotas.duplicatas(saida).tolist() == [None, "antiga:a", None, None, None, None]
    assert saida["folder"].tolist()[0] == "Montevidéu"
    # "1399. 1401" é intervalo de documentos, não data; "1402. 1660" e "2950. 1701" têm ano
    # e o ano entre colchetes, quando há, é o que vale
    assert saida["ano_isolado"].tolist()[1] == 1722
    assert pd.isna(saida["ano_isolado"][2])
    assert saida["ano_isolado"].tolist()[3:] == [1660, 1701, 1660]
    assert contagem["ano_falso_corrigido"] == 2


def test_bloco_de_cota_repetida_curado_pelo_digitarq():
    indice = compat.IndiceDigitArq([f"PT/AHU/CU/011/0013/{n:05d}" for n in range(1066, 1070)])
    base = pd.DataFrame({
        "colecao": ["ahu-brasil"] * 4 + ["ahu-brasil"] * 3,
        "new_code": ["AHU_CU_011, Cx. 13, D. 1065."] * 4 + ["AHU_CU_022, Cx. 1, D. 3."] * 3,
        "reference_code": [None] * 7,
        "document_id_and_date": ["1066. 1728", "1067. 1728", "1068. 1728", "1069. 1728",
                                 "3. 1700", "4. 1700", "5. 1700"],
    })
    saida, contagem = cotas.ajustar(base, indice)
    assert contagem["cota_em_bloco_curada"] == 4
    assert saida["new_code"].tolist()[:4] == [f"AHU_CU_011, Cx. 13, D. {n}." for n in range(1066, 1070)]
    assert saida["reference_code"].tolist()[0] == "PT/AHU/CU/011/0013/01066"
    # sem prova no DigitArq, o bloco fica como veio
    assert saida["new_code"].tolist()[4:] == ["AHU_CU_022, Cx. 1, D. 3."] * 3


def test_lista_ignore(tmp_path):
    arq = tmp_path / "duplicatas.ignore"
    arq.write_text("# cabeçalho\nahu-brasil:b  # repete antiga:a | AHU_CU_012, Cx. 1, D. 36.\n"
                   "ahu-brasil:x\n\n", encoding="utf-8")
    assert cotas.ler_ignorados(arq) == {"ahu-brasil:b": "antiga:a", "ahu-brasil:x": ""}
    assert cotas.ler_ignorados(tmp_path / "nao_existe.ignore") == {}


def test_cota_corrigida_guarda_a_impressa_e_troca_cota_e_pasta(tmp_path):
    """corpus/cotas_corrigidas.tsv: a cota impressa vai para `cota_na_fonte`; cota, referência e
    pasta passam a ser as certas; o resumo não muda."""
    import pandas as pd

    from build import cotas

    tsv = tmp_path / "cotas_corrigidas.tsv"
    tsv.write_text("# comentário\ndoc_uid\tcota\tpasta\tmotivo\n"
                   "a\tAHU_CU_003, Cx. 2, D. 173.\tBrasil Geral\terro tipográfico\n"
                   "b\tAHU_ACL_CU_022, Cx. 3, D. 273.\t\tcaixa trocada\n", encoding="utf-8")
    base = pd.DataFrame({"doc_uid": ["a", "b", "c"],
                         "new_code": ["AHU_CU_022, Cx. 2, D. 173.", "AHU_ACL_CU_022, Cx. 2, D. 273.",
                                      "AHU_CU_003, Cx. 1, D. 1."],
                         "reference_code": ["PT/AHU/CU/022/0002/00173", "PT/AHU/CU/022/0002/00273",
                                            "PT/AHU/CU/003/0001/00001"],
                         "folder": ["Sergipe d’el-Rei", "Sergipe d’el-Rei", "Brasil Geral"],
                         "description": ["x", "y", "z"]})
    nova, n = cotas.aplicar_corrigidas(base, cotas.ler_corrigidas(tsv))
    assert n == 2
    assert nova["reference_code"].tolist() == ["PT/AHU/CU/003/0002/00173", "PT/AHU/CU/022/0003/00273",
                                               "PT/AHU/CU/003/0001/00001"]
    assert nova["cota_na_fonte"].tolist()[:2] == ["AHU_CU_022, Cx. 2, D. 173.",
                                                  "AHU_ACL_CU_022, Cx. 2, D. 273."]
    assert pd.isna(nova["cota_na_fonte"].iloc[2])
    assert nova["folder"].tolist() == ["Brasil Geral", "Sergipe d’el-Rei", "Brasil Geral"]
    assert nova["description"].tolist() == base["description"].tolist()
    assert cotas.aplicar_corrigidas(base, cotas.ler_corrigidas(tmp_path / "nao_existe.tsv"))[1] == 0
