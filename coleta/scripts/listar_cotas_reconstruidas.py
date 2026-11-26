"""Lista os documentos cuja cota foi montada pelo catálogo, e não copiada da fonte.

Até 24/11/2026 eram os 491 verbetes do inventário de Sergipe (página "Avulsos - Sergipe
(1619-1822)" do gov.br), cuja cota o `parse_sergipe.py` montava com a Caixa e o Documento da
edição impressa (a numeração antiga, 9 caixas). Desde então o parser dá a cota oficial do
AHU/DigitArq (6 caixas, documento = número do verbete; ver `parse_sergipe.caixa_oficial_022`) e
guarda a numeração impressa em `old_code`; nenhum verbete sai marcado, e a lista fica vazia.
Cotas que a fonte imprime erradas (erro tipográfico, caixa trocada) não entram aqui: vão para
`corpus/cotas_corrigidas.tsv`, com a cota certa e a prova.

O script lê os verbetes extraídos (`*.jsonl` do `parse_*`), pega os marcados com
`cota_reconstruida` e acha os documentos da coleção que vieram deles (mesma página de origem em
`caminho_resgate` e mesmo `new_code`). Grava `corpus/cotas_reconstruidas.ignore`, que o
`build/construir_app.py` usa para tirar os links desses documentos e marcar a cota como não oficial.

Uso: python coleta/scripts/listar_cotas_reconstruidas.py VERBETES.jsonl [...]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
COLECAO = RAIZ / "corpus" / "colecoes" / "ahu-brasil" / "documentos.parquet"
SAIDA = RAIZ / "corpus" / "cotas_reconstruidas.ignore"
CABECALHO = """\
# Documentos cuja cota foi montada pelo catálogo, sem cota oficial na fonte
# (coleta/scripts/listar_cotas_reconstruidas.py). O app não dá link de acesso a eles e avisa que a
# cota não é oficial. Formato: doc_uid  # cota montada. Apague a linha quando a cota for corrigida.
# Cotas impressas erradas na fonte não entram aqui: ficam em corpus/cotas_corrigidas.tsv, com prova.
"""


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("verbetes", nargs="+", type=Path)
    args = p.parse_args()

    marcados: set[tuple[str, str]] = set()
    for arq in args.verbetes:
        for linha in arq.read_text(encoding="utf-8").splitlines():
            v = json.loads(linha)
            if v.get("cota_reconstruida"):
                marcados.add((v["caminho_resgate"], v["new_code"]))

    docs = pd.read_parquet(COLECAO, columns=["doc_uid", "new_code", "caminho_resgate"])
    chave = list(zip(docs["caminho_resgate"], docs["new_code"]))
    achados = docs[[c in marcados for c in chave]]
    faltam = marcados - set(zip(achados["caminho_resgate"], achados["new_code"]))
    if faltam:
        raise SystemExit(f"{len(faltam)} verbetes marcados não estão na coleção "
                         f"(ex.: {sorted(faltam)[0]}).")
    linhas = [f"{u}  # {c}" for u, c in zip(achados["doc_uid"], achados["new_code"])]
    SAIDA.write_text(CABECALHO + "".join(f"{linha}\n" for linha in linhas), encoding="utf-8")
    print(f"{len(linhas)} documentos em {SAIDA.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
