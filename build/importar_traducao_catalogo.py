"""importar_traducao_catalogo.py — camada `traducao_en_catalogo_v1`: a tradução inglesa feita pelo
próprio catálogo para os resumos que o MAPE não traduz.

A tradução do MAPE (camada `mape_en_v6`) cobre 141.796 documentos. Os outros (só no catálogo, sem
código de referência, ou com resumo diferente do MAPE) foram traduzidos pelo catálogo com o Gemini,
pela linha de comando `agy`, com o comando de `coleta/traducao_en/PROMPT.md` (glossário fixo de
tipologias e cargos, nomes como na fonte). Ver `coleta/traducao_en/`.

Esta camada é separada da do MAPE e aparece marcada como tradução automática do catálogo. O app só
a usa onde não há tradução do MAPE ligada.

Entrada : a pasta de saída de `traduzir.py rodar` (lote_*.json) ou o pacote .jsonl.gz
          (uma linha por documento: doc_uid, en, modelo, data)
Saídas  : corpus/camadas/traducao_en_catalogo_v1/traducao.parquet (doc_uid, resumo_en, modelo,
                                                                   data)
          corpus/camadas/traducao_en_catalogo_v1/camada.json
          corpus/manifest.json

Uso: python build/importar_traducao_catalogo.py --entrada coleta/traducao_en/traducao_en_catalogo_v1.jsonl.gz
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from build.importar_base import ErroImportacao, commit_atual, sha256_arquivo  # noqa: E402
from build.importar_camadas import gravar_camada, registrar_no_manifesto  # noqa: E402

VERSAO_SCRIPT = "1.0.0"
CAMADA = "traducao_en_catalogo_v1"
ARQUIVO = "traducao.parquet"
PROMPT = RAIZ / "coleta" / "traducao_en" / "PROMPT.md"


def ler_entrada(entrada: Path) -> pd.DataFrame:
    linhas = []
    if entrada.is_dir():
        for arq in sorted(entrada.glob("lote_*.json")):
            dados = json.loads(arq.read_text(encoding="utf-8"))
            for d in dados["docs"]:
                linhas.append({"doc_uid": d["doc_uid"], "resumo_en": d["en"],
                               "modelo": dados["modelo"], "data": dados["data"]})
    else:
        with gzip.open(entrada, "rt", encoding="utf-8") as f:
            for linha in f:
                d = json.loads(linha)
                linhas.append({"doc_uid": d["doc_uid"], "resumo_en": d["en"],
                               "modelo": d["modelo"], "data": d["data"]})
    if not linhas:
        raise ErroImportacao(f"Nenhuma tradução em {entrada}.")
    df = pd.DataFrame(linhas)
    df["resumo_en"] = df["resumo_en"].astype(str).str.split().str.join(" ")
    df = df[df["resumo_en"] != ""]
    repetidos = df["doc_uid"].duplicated(keep="last")
    return df[~repetidos].sort_values("doc_uid").reset_index(drop=True)


def importar(entrada: Path, corpus: Path) -> dict:
    entrada, corpus = Path(entrada), Path(corpus)
    if not entrada.exists():
        raise ErroImportacao(f"Entrada não encontrada: {entrada}")
    df = ler_entrada(entrada)
    modelos = sorted(df["modelo"].unique())
    camada = {
        "nome": CAMADA,
        "tipo": "traducao_en_catalogo",
        "versao": "1",
        "fonte": {
            "descricao": "tradução automática feita pelo catálogo para os resumos sem tradução do "
                         "MAPE; não revisada",
            "modelos": modelos,
            "rota": "Google Gemini pela linha de comando agy (assinatura AI Pro)",
            "comando": "coleta/traducao_en/PROMPT.md",
            "comando_sha256": sha256_arquivo(PROMPT) if PROMPT.exists() else None,
            "licenca": "CC BY 4.0 (a tradução); o resumo traduzido segue a licença do AHU/ACTD",
        },
        "regra_uso": "o app usa esta tradução só onde a camada traducao_en (MAPE) não tem tradução "
                     "ligada; ela aparece marcada como tradução automática do catálogo",
        "processo": {"script": "build/importar_traducao_catalogo.py",
                     "versao_script": VERSAO_SCRIPT, "commit": commit_atual()},
        "entrada": {"arquivo": entrada.name,
                    "sha256": None if entrada.is_dir() else sha256_arquivo(entrada)},
    }
    pasta = corpus / "camadas" / CAMADA
    camada = gravar_camada(pasta, ARQUIVO, df, camada)
    registrar_no_manifesto(corpus, pasta, camada, (ARQUIVO, "camada.json"))
    return camada


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--entrada", required=True, type=Path)
    ap.add_argument("--corpus", default=RAIZ / "corpus", type=Path)
    args = ap.parse_args()
    try:
        camada = importar(args.entrada, args.corpus)
    except ErroImportacao as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 1
    print(f"{CAMADA}: {camada['documentos']} traduções ({', '.join(camada['fonte']['modelos'])})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
