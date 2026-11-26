"""Recupera links do DocReader que a junção por (caixa, documento) perdeu.

A sondagem de 21/11/2026 no andeca mostrou que o rótulo da BN às vezes traz a caixa errada
(`Cx. 144` para um documento da caixa 145 do catálogo). Nas séries de numeração contínua, o número
do documento basta: se um número aparece uma só vez no rolo, uma só vez na série do catálogo, o
documento está sem link e a caixa da BN difere da do catálogo em no máximo 2, o quadro é dele.
Quadros já usados por outro documento do catálogo ficam de fora.

Também liga os verbetes da série 081 ("Sergipe"), que repetem verbetes da 022: a cota antiga do
081 é a referência da 022, e o 081 recebe o quadro dela.

Acrescenta as linhas novas a `corpus/resgate_docreader.tsv.gz`; depois rode
`coleta/scripts/aplicar_indice_resgate.py`.

Uso: python coleta/scripts/casar_por_numero.py [--dry-run]
"""
from __future__ import annotations

import argparse
import gzip
import re
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
INDICE = RAIZ / "corpus" / "resgate_docreader.tsv.gz"
DOCS = RAIZ / "app_dados" / "documentos.parquet"
TSV = RAIZ / "coleta" / "docreader"
# Rolos de numeração contínua por série (sem os rolos com mapeamento especial).
ROLOS = {"003_BG_AV": "003", "005_BA_AV": "005", "005_BA_LF": "005-002", "009_MA": "009",
         "013_PA": "013", "015_PE": "015", "017_RJ_AV": "017", "023-1_SP_MG": "023-001",
         "023_SP_AV": "023", "089_CU": "089", "089_UL_AV": "035"}
MAX_DIF_CAIXA = 2
RE_ANTIGA = re.compile(r"cx\s*\.?\s*0*(\d+)\s*,?\s*doc\.?\s*0*(\d+)\s*-?\s*([A-Za-z]?)\s*\.?\s*$", re.I)


def ler_indice() -> pd.DataFrame:
    return pd.read_csv(INDICE, sep="\t", dtype=str)


def por_numero(docs: pd.DataFrame, usados: set[str]) -> list[tuple[str, str, str]]:
    novas = []
    for bib, serie in ROLOS.items():
        t = pd.read_csv(TSV / f"resgate_pagfis_{bib}.tsv.gz", sep="\t", dtype=str)
        t["cx"] = pd.to_numeric(t["caixa"], errors="coerce")
        t["dn"] = pd.to_numeric(t["doc"].str.extract(r"^(\d+)")[0], errors="coerce")
        t = t[~(bib + "#" + t["pagfis"]).isin(usados)]
        t = t[t["dn"].map(t["dn"].value_counts()) == 1]
        s = docs[docs["serie"] == serie]
        unicos = s["doc"].map(s["doc"].value_counts()) == 1
        falta = s[unicos & s["quadro"].isna() & s["doc"].notna()]
        m = falta.merge(t[["dn", "cx", "pagfis"]].rename(columns={"dn": "doc", "cx": "cx_bn"}), on="doc")
        m = m[(m["cx_bn"] - m["cx"]).abs() <= MAX_DIF_CAIXA]
        novas += [(r, bib, p) for r, p in zip(m["reference_code"], m["pagfis"])]
    return novas


def sergipe_081(docs: pd.DataFrame) -> list[tuple[str, str, str]]:
    """Cada verbete 081 repete um da 022: a cota antiga (cx. N doc. M) é a referência 022/N/M, de
    numeração local por caixa. O 081 recebe o quadro desse verbete da 022, se ele tiver. (A tabela
    do gov.br não serve de chave: a mesma cota antiga aparece em várias linhas.)"""
    quadro = dict(zip(docs["reference_code"], docs["quadro"]))
    novas = []
    for ref, antiga, q in zip(docs["reference_code"], docs["old_code"], docs["quadro"]):
        if not isinstance(ref, str) or "/081/" not in ref or isinstance(q, str):
            continue
        m = RE_ANTIGA.search(antiga or "")
        if not m or m.group(3):
            continue
        par = quadro.get(f"PT/AHU/CU/022/{int(m.group(1)):04d}/{int(m.group(2)):05d}")
        if isinstance(par, str):
            bib, pagfis = par.split("#", 1)
            novas.append((ref, bib, pagfis))
    return novas


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    docs = pd.read_parquet(DOCS, columns=["reference_code", "old_code", "resgate_docreader"])
    partes = docs["reference_code"].str.split("/", expand=True)
    docs["serie"], docs["cx"] = partes[3], pd.to_numeric(partes[4], errors="coerce")
    docs["doc"] = pd.to_numeric(partes[5].str.split(".").str[0], errors="coerce")
    docs["quadro"] = docs["resgate_docreader"]
    indice = ler_indice()
    # Só contam como usados os quadros de documentos que o catálogo tem: o índice também guarda os
    # rótulos da BN cuja cota (com a caixa errada) não existe no catálogo.
    usados = set(docs["quadro"].dropna())
    ja = set(indice["referencia"])
    novas = [n for n in por_numero(docs, usados) + sergipe_081(docs) if n[0] not in ja]
    print(f"linhas novas: {len(novas)}")
    for bib in sorted({b for _, b, _ in novas}):
        print(f"  {bib}: {sum(b == bib for _, b, _ in novas)}")
    if args.dry_run or not novas:
        return 0
    with gzip.open(INDICE, "at", encoding="utf-8") as f:
        for ref, bib, pagfis in novas:
            f.write(f"{ref}\t{bib}\t{pagfis}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
