"""atualizar_compat.py — refaz a concordância de cotas antigas e o `compat/camada.json`.

O módulo de compatibilidade (`compat/`) é publicado sem nenhuma base. Duas tarefas de manutenção:

* `--concordancia <documentos.parquet da base do ACTD>`: refaz `compat/dados/concordancia_cota_antiga.tsv.gz`
  (código de referência -> cota antiga) a partir das cotas impressas nos catálogos do ACTD. Só
  identificadores saem: nenhum resumo. Quando um código tem mais de uma cota antiga, fica a
  primeira em ordem alfabética;
* sempre: regrava `compat/camada.json` com a versão, a licença e o SHA-256 e o número de linhas de
  cada tabela. O teste `tests/test_compat.py` confere esses hashes.

Uso:
    python scripts/atualizar_compat.py
    python scripts/atualizar_compat.py --concordancia /caminho/dados-actd/app_dados/documentos.parquet
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import compat  # noqa: E402

CABECALHO_CONCORDANCIA = (
    "# Concordância código de referência -> cota antiga (numeração anterior do AHU), tirada das cotas\n"
    "# impressas nos catálogos do ACTD. Só identificadores. Quando um código tem mais de uma cota antiga,\n"
    "# fica a primeira em ordem alfabética. Gerada por scripts/atualizar_compat.py.\n"
)
TABELAS = {
    "resgate_docreader.tsv.gz": "código de referência -> rolo (bib) e quadro (pagfis) do DocReader "
                                "do Projeto Resgate; dos links do gov.br e da varredura do DocReader "
                                "(coleta/docreader/)",
    "digitarq_referencias.tsv.gz": "registros do DigitArq (PT/AHU/CU), listados caixa a caixa "
                                   "(coleta/scripts/varrer_digitarq.py)",
    "resgate_codices.tsv": "primeiro e último quadro de cada Códice no rolo CODICES do DocReader",
    "concordancia_cota_antiga.tsv.gz": "código de referência -> cota antiga, das cotas impressas nos "
                                       "catálogos do ACTD (só identificadores)",
}


def concordancia(documentos: Path) -> int:
    import pandas as pd

    from ahu.links import limpar_cota

    d = pd.read_parquet(documentos, columns=["reference_code", "old_code"])
    d = d[d["reference_code"].astype(str).str.startswith("PT/") & d["old_code"].notna()]
    d = d.assign(antiga=d["old_code"].map(limpar_cota))
    d = d[d["antiga"] != ""]
    pares = d.groupby("reference_code")["antiga"].agg(lambda s: sorted(set(s))[0])
    with gzip.open(compat.PASTA / "concordancia_cota_antiga.tsv.gz", "wt", encoding="utf-8") as f:
        f.write(CABECALHO_CONCORDANCIA)
        f.write("referencia\tcota_antiga\n")
        for ref, antiga in pares.sort_index().items():
            f.write(f"{ref}\t{antiga}\n")
    return int(len(pares))


def linhas(arq: Path) -> int:
    abrir = gzip.open if arq.suffix == ".gz" else open
    with abrir(arq, "rt", encoding="utf-8") as f:
        return sum(1 for linha in f if linha.startswith(("PT/",)) or linha[:1].isdigit())


def sha256(arq: Path) -> str:
    return hashlib.sha256(arq.read_bytes()).hexdigest()


def camada() -> dict:
    return {
        "nome": "compat", "tipo": "compatibilidade", "versao": compat.VERSAO,
        "atualizado_em": date.today().isoformat(),
        "descricao": "Módulo de compatibilidade do Catálogo AHU-Brasil: liga cada cota do AHU à "
                     "imagem no Projeto Resgate (DocReader da Biblioteca Nacional), ao registro do "
                     "DigitArq e à cota antiga. Serve a qualquer base que traga o código de "
                     "referência PT/AHU/CU.",
        "licenca": "CC BY 4.0",
        "credito": "Pacheco Rocha, S. R. Catálogo AHU-Brasil, módulo de compatibilidade (2026). "
                   "doi:10.5281/zenodo.18772666. CC BY 4.0.",
        "tabelas": {nome: {"descricao": desc, "linhas": linhas(compat.PASTA / nome),
                           "sha256": sha256(compat.PASTA / nome)}
                    for nome, desc in TABELAS.items()},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--concordancia", help="documentos.parquet da base do ACTD")
    a = ap.parse_args()
    if a.concordancia:
        print(f"concordância: {concordancia(Path(a.concordancia))} códigos")
    c = camada()
    (RAIZ / "compat" / "camada.json").write_text(
        json.dumps(c, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for nome, t in c["tabelas"].items():
        print(f"{nome}: {t['linhas']} linhas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
