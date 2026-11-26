"""Layout do catálogo de Sergipe (gov.br, 1619–1822): número do verbete (1–495),
'Caixa: 01, Documento Nº: 86, 1700, junho, 16, Lisboa' (ou 'Caixa: 02Identificação: 27, ...') e resumo.

A página do gov.br traz a caixa e o documento da edição impressa (9 caixas), mas no AHU/DigitArq
(série 022) os 495 documentos estão numerados em sequência de 1 a 495 em 6 caixas:
Cx. 1 = 1–106, Cx. 2 = 107–195, Cx. 3 = 196–287, Cx. 4 = 288–362, Cx. 5 = 363–432, Cx. 6 = 433–495.
O parser grava a cota oficial AHU em `new_code` e preserva a numeração da edição impressa em `old_code`.
"""
import re

CAB = re.compile(
    r"^Caixa\s*:?\s*(\d+)\s*(?:,\s*Documento\s*N[º°o]?|Identifica[çc][ãa]o)\s*:?\s*(\d+)\s*(?:-\s*([A-Z]))?\s*,?\s*(.*)$",
    re.I,
)
RODAPE_PAGINA = re.compile(r"\s*Elaboração\s+e\s+revisão\s+dos\s+verbetes\s*:.*$", re.I | re.S)

CAIXAS_OFICIAIS_022 = (
    (1, 106, 1),
    (107, 195, 2),
    (196, 287, 3),
    (288, 362, 4),
    (363, 432, 5),
    (433, 495, 6),
)


def caixa_oficial_022(verbete: int) -> int | None:
    """Caixa oficial do AHU/DigitArq para o número sequencial do verbete de Sergipe (1–495)."""
    for ini, fim, cx in CAIXAS_OFICIAIS_022:
        if ini <= verbete <= fim:
            return cx
    return None


def parse(texto, url, serie="022"):
    linhas = [l.strip() for l in texto.splitlines() if l.strip()]
    out = []
    for i, l in enumerate(linhas):
        m = CAB.match(l)
        if not m:
            continue
        num = linhas[i - 1] if i and re.fullmatch(r"\d+[A-Z]?", linhas[i - 1]) else None
        desc = []
        for nl in linhas[i + 1:]:
            if CAB.match(nl) or re.fullmatch(r"\d+[A-Z]?", nl):
                break
            desc.append(nl)
        d = RODAPE_PAGINA.sub("", " ".join(desc)).strip()
        anexo = re.search(r"\((Anexos?\s*:?\s*[^)]*)\)\.?\s*$", d)
        cx_imp, doc_imp, suf_imp = int(m.group(1)), int(m.group(2)), m.group(3) or ""
        old_code = f"AHU-Sergipe, cx. {cx_imp:02d}, doc. {doc_imp:02d}{suf_imp}."

        num_int = int(num) if (num and num.isdigit()) else None
        cx_of = caixa_oficial_022(num_int) if num_int is not None else None
        if cx_of is not None and num_int is not None:
            new_code = f"AHU_ACL_CU_{serie}, Cx. {cx_of}, D. {num_int}."
            chave_cota = f"{serie}|{cx_of}|{num_int}"
            reconstruida = False
        else:
            new_code = f"AHU_ACL_CU_{serie}, Cx. {cx_imp}, D. {doc_imp}{suf_imp}."
            chave_cota = f"{serie}|{cx_imp}|{doc_imp}{suf_imp}"
            reconstruida = True

        out.append({
            "numero": num,
            "data_local": m.group(4).strip() or None,
            "description": d,
            "anexos": re.sub(r"^Anexos?\s*:?\s*", "", anexo.group(1)) if anexo else None,
            "old_code": old_code,
            "new_code": new_code,
            "cota_reconstruida": reconstruida,
            "observacoes": [],
            "caminho_resgate": url,
            "chave_cota": chave_cota,
            "tipologia_lite": (d.split()[0].strip(",.").upper() if d else None),
        })
    return out
