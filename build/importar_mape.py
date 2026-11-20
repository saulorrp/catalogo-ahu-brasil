"""importar_mape.py — camada `mape_en_v4`: a tradução inglesa dos resumos feita pelo projeto MAPE.

Fonte: *Mapping the Atlantic Portuguese Empire* (MAPE), de Agata Błoch, Demival Vasques Filho,
Michał Bojanowski, Clodomir Santana e Saddam Hussain. Dataset no Zenodo, versão 4 (15/09/2025),
doi:10.5281/zenodo.15481608, licença CC BY 4.0. O arquivo usado é o CSV bilíngue
`MAPE_dataset_2025_Bilingual_v2.csv` (a primeira linha diz "MetaData" e é pulada).

O MAPE transcreveu os mesmos catálogos do AHU publicados no ACTD. Cada verbete do MAPE se liga a
um documento do catálogo pelo código de referência (`PT/AHU/CU/…`), normalizado pelo
`ahu/conversor.py` dos dois lados (o MAPE escreve `…/0101/7581`, o catálogo `…/0101/07581`).

A tradução só é ligada quando o resumo português do MAPE é o mesmo do catálogo: semelhança de
pelo menos `LIMIAR_SEMELHANCA` entre os dois textos normalizados. Abaixo disso o par fica na
camada, com a semelhança, mas a tradução não vai para o app: um código igual com texto diferente
indica cota repetida ou erro de uma das fontes, e é assunto da auditoria cruzada, não da ficha.

Entrada : o CSV do MAPE (não vai para o repositório: 142 MB; o sha256 fica no camada.json)
Saídas  : corpus/camadas/mape_en_v4/mape.parquet  (doc_uid, mape_doc_id, mape_reference_code,
                                                    mape_ano, semelhanca, ligado, resumo_en)
          corpus/camadas/mape_en_v4/camada.json    (fonte, crédito, licença, regra, contagens)
          corpus/manifest.json

Uso: python build/importar_mape.py --entrada MAPE_dataset_2025_Bilingual_v2.csv
"""
from __future__ import annotations

import argparse
import difflib
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from ahu import conversor  # noqa: E402
from build.importar_base import ErroImportacao, commit_atual, sha256_arquivo  # noqa: E402
from build.importar_camadas import gravar_camada, registrar_no_manifesto  # noqa: E402

VERSAO_SCRIPT = "1.0.0"
CAMADA_MAPE = "mape_en_v4"
LIMIAR_SEMELHANCA = 0.9
COLUNA_EN = "English Translation  (Doc_Text_Port)"  # com dois espaços, como no CSV

FONTE = {
    "titulo": "Mapping the Atlantic Portuguese Empire (MAPE) dataset",
    "autores": ["Agata Błoch", "Demival Vasques Filho", "Michał Bojanowski", "Clodomir Santana",
                "Saddam Hussain"],
    "versao": "4",
    "publicado_em": "2025-09-15",
    "doi": "10.5281/zenodo.15481608",
    "url": "https://doi.org/10.5281/zenodo.15481608",
    "licenca": "CC BY 4.0",
    "credito": "Tradução inglesa: Błoch, A.; Vasques Filho, D.; Bojanowski, M.; Santana, C.; "
               "Hussain, S. Mapping the Atlantic Portuguese Empire (MAPE) dataset, v4, 2025. "
               "Zenodo, doi:10.5281/zenodo.15481608. CC BY 4.0.",
}


def chave_referencia(*valores) -> str | None:
    """O código de referência normalizado do primeiro valor que o conversor reconhece."""
    for v in valores:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            continue
        cota = conversor.reconhecer(str(v))
        if cota is not None:
            ref = conversor.para_referencia(cota)
            if ref:
                return ref
    return None


def texto_comparavel(texto) -> str:
    """Minúsculas, sem acento, sem pontuação nem colchetes: só para comparar resumos."""
    if texto is None or (isinstance(texto, float) and pd.isna(texto)):
        return ""
    t = unicodedata.normalize("NFKD", str(texto))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", t)).strip()


def semelhanca(a, b) -> float:
    a, b = texto_comparavel(a), texto_comparavel(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def ler_mape(entrada: Path) -> pd.DataFrame:
    if not entrada.exists():
        raise ErroImportacao(f"CSV do MAPE não encontrado: {entrada}")
    m = pd.read_csv(entrada, skiprows=1, low_memory=False, dtype={"doc_number": str})
    faltam = {"doc_id", "reference_code", "year", "Doc_Text_Port", COLUNA_EN} - set(m.columns)
    if faltam:
        raise ErroImportacao(f"O CSV do MAPE não tem as colunas {sorted(faltam)}.")
    m["chave"] = m["reference_code"].map(chave_referencia)
    return m


def ler_base(corpus: Path) -> pd.DataFrame:
    partes = [pd.read_parquet(p) for p in sorted((corpus / "colecoes").glob("*/documentos.parquet"))]
    if not partes:
        raise ErroImportacao("Nenhuma coleção no corpus. Importe a coleção antes.")
    base = pd.concat(partes, ignore_index=True)
    base["chave"] = [chave_referencia(r, n) for r, n in zip(base["reference_code"], base["new_code"])]
    return base


def parear(base: pd.DataFrame, mape: pd.DataFrame) -> pd.DataFrame:
    """Um par por documento do catálogo cuja chave existe no MAPE."""
    m = mape.dropna(subset=["chave"]).drop_duplicates("chave").set_index("chave")
    linhas = []
    for uid, chave, resumo in zip(base["doc_uid"], base["chave"], base["description"]):
        if chave is None or chave not in m.index:
            continue
        r = m.loc[chave]
        s = semelhanca(resumo, r["Doc_Text_Port"])
        ano = pd.to_numeric(r["year"], errors="coerce")
        en = r[COLUNA_EN]
        linhas.append({
            "doc_uid": uid,
            "mape_doc_id": int(r["doc_id"]),
            "mape_reference_code": str(r["reference_code"]),
            "mape_ano": None if pd.isna(ano) else int(ano),
            "semelhanca": round(float(s), 4),
            "ligado": bool(s >= LIMIAR_SEMELHANCA and isinstance(en, str) and en.strip()),
            "resumo_en": en.strip() if isinstance(en, str) else None,
        })
    df = pd.DataFrame(linhas, columns=["doc_uid", "mape_doc_id", "mape_reference_code", "mape_ano",
                                       "semelhanca", "ligado", "resumo_en"])
    df["mape_ano"] = df["mape_ano"].astype("Int64")
    return df


def importar_mape(entrada: Path, corpus: Path) -> dict:
    entrada, corpus = Path(entrada), Path(corpus)
    mape = ler_mape(entrada)
    base = ler_base(corpus)
    df = parear(base, mape)
    pasta = corpus / "camadas" / CAMADA_MAPE
    faixas = pd.cut(df["semelhanca"], [-0.01, 0.5, 0.8, 0.9, 0.999, 1.0],
                    labels=["<0,5", "0,5–0,8", "0,8–0,9", "0,9–1", "1"]).value_counts()
    camada = gravar_camada(pasta, "mape.parquet", df, {
        "nome": CAMADA_MAPE,
        "tipo": "traducao_en",
        "versao": "4",
        "fonte": FONTE,
        "regra_pareamento": "código de referência normalizado por ahu/conversor.py dos dois lados "
                            "(no catálogo, reference_code ou, sem ele, new_code)",
        "regra_ligacao": f"semelhança (difflib, textos sem acento e sem pontuação) >= "
                         f"{LIMIAR_SEMELHANCA} entre o resumo do catálogo e o Doc_Text_Port do MAPE",
        "contagens": {
            "mape_verbetes": int(len(mape)),
            "mape_sem_codigo_reconhecido": int(mape["chave"].isna().sum()),
            "catalogo_documentos": int(len(base)),
            "pareados": int(len(df)),
            "ligados": int(df["ligado"].sum()),
            "por_faixa_de_semelhanca": {str(k): int(v) for k, v in faixas.items()},
        },
        "processo": {"script": "build/importar_mape.py", "versao_script": VERSAO_SCRIPT,
                     "commit": commit_atual()},
        "entrada": {"arquivo": entrada.name, "sha256": sha256_arquivo(entrada)},
    })
    registrar_no_manifesto(corpus, pasta, camada, ("mape.parquet", "camada.json"))
    return camada["contagens"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--entrada", required=True)
    ap.add_argument("--corpus", default=str(RAIZ / "corpus"))
    args = ap.parse_args()
    try:
        contagens = importar_mape(Path(args.entrada), Path(args.corpus))
    except ErroImportacao as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 1
    for k, v in contagens.items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
