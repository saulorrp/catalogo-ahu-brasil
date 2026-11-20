"""importar_mape.py — camada `mape_en_v6`: a tradução inglesa dos resumos feita pelo projeto MAPE.

Fonte: *MAPE: A Dataset of Correspondence from the Portuguese Empire* (Mapping the Atlantic
Portuguese Empire), de Agata Błoch, Demival Vasques Filho, Michał Bojanowski, Clodomir Santana,
Saddam Hussain, Apolinary Rzońca e Artur Podsiadły. Zenodo, versão 6 (20/11/2026),
doi:10.5281/zenodo.24403753 (DOI de conceito 10.5281/zenodo.15336798), licença CC BY 4.0.
Arquivo: `mape_dataset_version_6.csv`. O script também lê o CSV bilíngue da versão 2, cuja
primeira linha diz "MetaData"; texto e tradução são idênticos nas duas versões.

A tradução é a do MAPE, **sem nenhuma alteração**: foi feita por eles com o Gemini 1.5 Flash, e
os erros dela, inclusive 13 registros em que ficou gravada a mensagem de erro da API, ficam como
estão. Uma versão nova do MAPE entra rodando este script com o CSV novo.

Cada verbete do MAPE se liga a um documento do catálogo pelo código de referência (`PT/AHU/CU/…`),
normalizado pelo `ahu/conversor.py` dos dois lados (o MAPE escreve `…/0101/7581`, o catálogo
`…/0101/07581`). A tradução só é ligada quando o resumo português do MAPE é o mesmo do catálogo
(semelhança de pelo menos `LIMIAR_SEMELHANCA`): um código igual com texto diferente indica que o
verbete não é o mesmo, e a tradução seria a de outro documento. Esses pares ficam na camada, com
a semelhança, para a auditoria cruzada.

Entrada : o CSV do MAPE (não vai para o repositório: 180 MB; o sha256 fica no camada.json)
Saídas  : corpus/camadas/mape_en_v6/mape.parquet  (doc_uid, mape_doc_id, mape_reference_code,
                                                    semelhanca, ligado, resumo_en)
          corpus/camadas/mape_en_v6/camada.json    (fonte, crédito, licença, regra, contagens)
          corpus/manifest.json

Uso: python build/importar_mape.py --entrada mape_dataset_version_6.csv
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
CAMADA_MAPE = "mape_en_v6"
LIMIAR_SEMELHANCA = 0.9
COLUNA_PT, COLUNA_EN = "doc_text_portuguese", "doc_text_english"
# Nomes das colunas no CSV da versão 2 (com dois espaços antes do parêntese, como lá).
COLUNAS_V2 = {"Doc_Text_Port": COLUNA_PT, "English Translation  (Doc_Text_Port)": COLUNA_EN}

AUTORES = ["Agata Błoch", "Demival Vasques Filho", "Michał Bojanowski", "Clodomir Santana",
           "Saddam Hussain", "Apolinary Rzońca", "Artur Podsiadły"]
FONTE = {
    "titulo": "MAPE: A Dataset of Correspondence from the Portuguese Empire",
    "projeto": "Mapping the Atlantic Portuguese Empire (MAPE)",
    "autores": AUTORES,
    "versao": "6",
    "publicado_em": "2026-11-20",
    "doi": "10.5281/zenodo.24403753",
    "doi_conceito": "10.5281/zenodo.15336798",
    "url": "https://doi.org/10.5281/zenodo.24403753",
    "licenca": "CC BY 4.0",
    "traducao": "feita pelo MAPE com o Google Gemini 1.5 Flash (descrição do dataset); "
                "reproduzida sem alterações",
    "credito": "Tradução inglesa: Błoch, A.; Vasques Filho, D.; Bojanowski, M.; Santana, C.; "
               "Hussain, S.; Rzońca, A.; Podsiadły, A. MAPE: A Dataset of Correspondence from the "
               "Portuguese Empire, v6, 2026. Zenodo, doi:10.5281/zenodo.24403753. CC BY 4.0.",
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
    with open(entrada, encoding="utf-8") as f:
        pular = 1 if f.readline().startswith("MetaData") else 0  # o CSV da versão 2
    m = pd.read_csv(entrada, skiprows=pular, low_memory=False, dtype={"doc_number": str})
    m = m.rename(columns=COLUNAS_V2)
    faltam = {"doc_id", "reference_code", COLUNA_PT, COLUNA_EN} - set(m.columns)
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
        s = semelhanca(resumo, r[COLUNA_PT])
        en = r[COLUNA_EN]
        linhas.append({
            "doc_uid": uid,
            "mape_doc_id": int(r["doc_id"]),
            "mape_reference_code": str(r["reference_code"]),
            "semelhanca": round(float(s), 4),
            "ligado": bool(s >= LIMIAR_SEMELHANCA and isinstance(en, str) and en.strip()),
            "resumo_en": en if isinstance(en, str) else None,  # como o MAPE publicou
        })
    return pd.DataFrame(linhas, columns=["doc_uid", "mape_doc_id", "mape_reference_code",
                                         "semelhanca", "ligado", "resumo_en"])


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
        "versao": "6",
        "fonte": FONTE,
        "regra_pareamento": "código de referência normalizado por ahu/conversor.py dos dois lados "
                            "(no catálogo, reference_code ou, sem ele, new_code)",
        "regra_ligacao": "tradução não vazia e semelhança (difflib, textos sem acento e sem "
                         f"pontuação) >= {LIMIAR_SEMELHANCA} entre o resumo do catálogo e o "
                         "texto português do MAPE",
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
