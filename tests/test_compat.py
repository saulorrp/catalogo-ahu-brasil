"""O módulo de compatibilidade (compat/): as tabelas que ligam uma cota ao Resgate e ao DigitArq,
para qualquer base, inclusive com os intervalos que o DigitArq e o MAPE usam."""
import pandas as pd

import compat

DOCREADER = {
    "PT/AHU/CU/017-001/0001/00009": "017-1_RJ#40",
    "PT/AHU/CU/017-001/0001/00012": "017-1_RJ#55",
    "PT/AHU/CU/021/0001/00004": "021_SC#37",
}
DIGITARQ = compat.IndiceDigitArq(["PT/AHU/CU/017-001/0001/00009.00019", "PT/AHU/CU/021/0001/00004"])


def test_numeros_de_um_codigo():
    assert compat.numeros("PT/AHU/CU/021/0001/00004") == ["PT/AHU/CU/021/0001/00004"]
    assert compat.numeros("PT/AHU/CU/017-001/0001/00009.00011") == [
        "PT/AHU/CU/017-001/0001/00009.00011", "PT/AHU/CU/017-001/0001/00009",
        "PT/AHU/CU/017-001/0001/00010", "PT/AHU/CU/017-001/0001/00011"]
    # intervalo anômalo (largo demais, invertido ou com letra): só o primeiro número
    assert compat.numeros("PT/AHU/CU/005-001/0023/04252.05254")[1:] == ["PT/AHU/CU/005-001/0023/04252"]
    assert compat.numeros("PT/AHU/CU/005-002/0011/01335.A")[1:] == ["PT/AHU/CU/005-002/0011/01335"]
    assert compat.numeros(None) == []


def test_quadro_do_intervalo_e_o_do_primeiro_numero_que_tiver_quadro():
    assert compat.procurar("PT/AHU/CU/017-001/0001/00009.00019", DOCREADER) == "017-1_RJ#40"
    assert compat.procurar("PT/AHU/CU/017-001/0001/00010.00013", DOCREADER) == "017-1_RJ#55"
    assert compat.procurar("PT/AHU/CU/017-001/0001/00020.00021", DOCREADER) is None


def test_ligar_uma_base_com_intervalos():
    base = pd.DataFrame({
        "reference_code": ["PT/AHU/CU/017-001/0001/00009.00019", "PT/AHU/CU/021/0001/00004", None],
        "new_code": ["AHU_ACL_CU_017-01, Cx. 1, D. 9-19.", "AHU_ACL_CU_021, Cx. 1, D. 4.",
                     "AHU_ACL_CU, Cód. 235, fl. 60v."],
        "old_code": [None, None, None],
    })
    tabelas = compat.Tabelas(digitarq=DIGITARQ, docreader=DOCREADER, codices={"235": "CODICES#21086"},
                             concordancia={"PT/AHU/CU/021/0001/00004": "AHU-Santa Catarina, cx. 1, doc. 3"})
    saida, contagem = compat.ligar(base, tabelas, cota_antiga=True)
    assert saida["referencia_digitarq"].tolist() == [
        "PT/AHU/CU/017-001/0001/00009.00019", "PT/AHU/CU/021/0001/00004", None]
    assert saida["resgate_docreader"].tolist() == ["017-1_RJ#40", "021_SC#37", "CODICES#21086"]
    assert saida["old_code"].tolist() == [None, "AHU-Santa Catarina, cx. 1, doc. 3", None]
    assert contagem["resgate_com_quadro"] == 3
    assert contagem["cota_antiga_da_concordancia"] == 1


def test_a_base_do_actd_guarda_a_propria_cota_antiga():
    base = pd.DataFrame({"reference_code": ["PT/AHU/CU/021/0001/00004"],
                         "new_code": ["AHU_ACL_CU_021, Cx. 1, D. 4."], "old_code": [None]})
    tabelas = compat.Tabelas(concordancia={"PT/AHU/CU/021/0001/00004": "AHU-Santa Catarina, cx. 1"})
    saida, contagem = compat.ligar(base, tabelas)
    assert saida["old_code"].isna().all() and "cota_antiga_da_concordancia" not in contagem


def test_as_tabelas_publicadas_carregam():
    t = compat.Tabelas.ler()
    assert t.docreader["PT/AHU/CU/017/0069/06420"] == "017_RJ_AV#49044"
    assert t.digitarq.achar("PT/AHU/CU/017-001/0016/03266")
    assert t.codices["235"] == "CODICES#21086"
    assert t.concordancia["PT/AHU/CU/000-021/0002/00090"] == "AHU-Santa Catarina, cx. 2, doc. 19"


def test_o_modulo_nao_traz_resumo():
    """compat/ é publicável: só identificadores, nunca texto de resumo."""
    for arq in compat.PASTA.iterdir():
        if arq.suffix == ".gz":
            import gzip
            with gzip.open(arq, "rt", encoding="utf-8") as f:
                cabecalho = [linha for linha in f if not linha.startswith("#")][0]
        else:
            cabecalho = arq.read_text(encoding="utf-8").splitlines()[0]
        assert "descri" not in cabecalho.lower() and "resumo" not in cabecalho.lower()


def test_camada_json_confere_com_as_tabelas():
    """compat/camada.json registra o SHA-256 de cada tabela (scripts/atualizar_compat.py)."""
    import hashlib
    import json

    camada = json.loads((compat.PASTA.parent / "camada.json").read_text(encoding="utf-8"))
    assert camada["licenca"] == "CC BY 4.0"
    for nome, info in camada["tabelas"].items():
        assert hashlib.sha256((compat.PASTA / nome).read_bytes()).hexdigest() == info["sha256"], nome
