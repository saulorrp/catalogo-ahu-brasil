"""construir_app.py — junta as camadas ativas nos artefatos que o app lê.

Entrada : corpus/ (base + camadas ativas, segundo o corpus/manifest.json)
Saídas  : app_dados/
              manifest.json        manifesto do corpus + camadas usadas + hash de cada artefato
              documentos.parquet   base + tipologia, uma linha por doc_uid
              embeddings/          parte_000.f16.npy, ...: linha i = documentos.parquet linha i
              lexico/              índice BM25 por campos em disco (ahu/lexico.py)

O que este script garante, para que o app não precise lembrar:
  * as coleções, as pastas e as tipologias saem dos dados: acrescentar uma coleção em
    `corpus/colecoes/` e reconstruir basta, sem tocar no código;
  * só entram dados das fontes (AHU via ACTD, Projeto Resgate, DigitArq) e cálculos
    determinísticos sobre eles.

Uso:
    python build/construir_app.py
    python build/construir_app.py --corpus corpus --saida app_dados
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from ahu import consulta_onnx  # noqa: E402
from ahu import lexico as mod_lexico  # noqa: E402
from ahu.texto import tokenizar  # noqa: E402
from build import cotas  # noqa: E402
from build.importar_base import ErroImportacao, commit_atual, sha256_arquivo  # noqa: E402

VERSAO_SCRIPT = "1.0.0"
VERSAO_ARTEFATOS = "1"

# Pesos iniciais. Calibrados no conjunto de teste.
PESOS_CAMPOS = {"tipologia": 1.5, "descricao": 1.0, "pasta": 0.5}

COLUNAS_BASE = ["doc_uid", "colecao", "folder", "description", "old_code", "new_code",
                "reference_code", "document_id_and_date", "ano_isolado",
                "referencia_digitarq", "resgate_docreader", "duplicata_de"]
COLUNAS_TIPOLOGIA = ["tipologia", "tipologia_chave", "typology_status"]


# ---------------------------------------------------------------------------
# Leitura das camadas ativas
# ---------------------------------------------------------------------------

def ler_manifesto(corpus: Path) -> dict:
    arq = corpus / "manifest.json"
    if not arq.exists():
        raise ErroImportacao(f"{arq} não existe. Rode build/importar_base.py antes.")
    with open(arq, encoding="utf-8") as f:
        return json.load(f)


def camada_ativa(manifesto: dict, tipo: str, obrigatoria: bool = True) -> str | None:
    """Nome da camada ativa de um tipo. O manifesto decide qual é, não o código."""
    ativas = [nome for nome, c in manifesto.get("camadas", {}).items()
              if c.get("tipo") == tipo and c.get("ativa")]
    if len(ativas) > 1:
        raise ErroImportacao(
            f"Há {len(ativas)} camadas de tipo '{tipo}' ativas ({', '.join(sorted(ativas))}). "
            "Deixe uma só ativa no corpus/manifest.json."
        )
    if not ativas:
        if obrigatoria:
            raise ErroImportacao(
                f"Nenhuma camada de tipo '{tipo}' está ativa no manifesto. "
                "Rode os scripts de construção do corpus."
            )
        return None
    return ativas[0]


def _ler_camada(pasta: Path) -> dict:
    arq = pasta / "camada.json"
    if not arq.exists():
        raise ErroImportacao(f"{arq} não existe. Reconstrua a camada.")
    with open(arq, encoding="utf-8") as f:
        return json.load(f)


def _ler_parquet(caminho: Path, o_que: str) -> pd.DataFrame:
    if not caminho.exists():
        raise ErroImportacao(f"{o_que} não encontrado: {caminho}. Reconstrua a camada.")
    return pd.read_parquet(caminho)


def ler_base(corpus: Path, manifesto: dict) -> pd.DataFrame:
    """Todas as coleções do manifesto, concatenadas na ordem em que aparecem."""
    partes = []
    for colecao in manifesto.get("colecoes", {}):
        caminho = corpus / "colecoes" / colecao / "documentos.parquet"
        partes.append(_ler_parquet(caminho, f"base da coleção {colecao}"))
    if not partes:
        raise ErroImportacao("O manifesto não tem nenhuma coleção. Rode build/importar_base.py.")
    base = pd.concat(partes, ignore_index=True)
    if not base["doc_uid"].is_unique:
        repetidos = base.loc[base["doc_uid"].duplicated(), "doc_uid"].head(3).tolist()
        raise ErroImportacao(f"doc_uid repetido entre coleções (ex.: {', '.join(repetidos)}).")
    return base


# ---------------------------------------------------------------------------
# documentos.parquet
# ---------------------------------------------------------------------------

def montar_documentos(base: pd.DataFrame, tipologia: pd.DataFrame) -> pd.DataFrame:
    """Base + tipologia normalizada, uma linha por doc_uid."""
    faltam = set(base["doc_uid"]) - set(tipologia["doc_uid"])
    if faltam:
        raise ErroImportacao(
            f"{len(faltam)} documentos da base não estão na camada de tipologia "
            f"(ex.: {', '.join(sorted(faltam)[:3])}). Reconstrua a camada."
        )
    docs = base[[c for c in COLUNAS_BASE if c in base.columns]].copy()
    return docs.merge(tipologia[["doc_uid", *COLUNAS_TIPOLOGIA]], on="doc_uid", how="left")


# ---------------------------------------------------------------------------
# lexico.pkl — BM25 por campos
# ---------------------------------------------------------------------------

def textos_por_campo(docs: pd.DataFrame) -> dict[str, list[str]]:
    """Um texto por documento e por campo, na ordem de `docs`."""
    def coluna(nome: str) -> list[str]:
        if nome not in docs.columns:
            return [""] * len(docs)
        return ["" if v is None or v is pd.NA else str(v) for v in docs[nome].fillna("")]

    return {
        "tipologia": coluna("tipologia"),
        "descricao": coluna("description"),
        "pasta": coluna("folder"),
    }


def construir_lexico(docs: pd.DataFrame, saida: Path) -> dict:
    """Índice BM25 por campo, gravado em disco para o app (ahu/lexico.py)."""
    textos = textos_por_campo(docs)
    tokens = {campo: [tokenizar(v) for v in valores] for campo, valores in textos.items()}
    vazios = {campo: int(sum(1 for t in linhas if not t)) for campo, linhas in tokens.items()}
    return mod_lexico.gravar(saida, tokens, PESOS_CAMPOS, vazios)


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------

def alinhar_embeddings(pasta_camada: Path, docs: pd.DataFrame) -> tuple[np.ndarray, dict]:
    """Reordena os vetores da camada para a ordem de `documentos.parquet`."""
    indice = _ler_parquet(pasta_camada / "indice.parquet", "índice de embeddings")
    arq = pasta_camada / "embeddings.f16.npy"
    if not arq.exists():
        raise ErroImportacao(f"Embeddings não encontrados: {arq}. Rode build/construir_indice.py.")
    emb = np.load(arq)
    if emb.shape[0] != len(indice):
        raise ErroImportacao(
            f"A camada de embeddings tem {emb.shape[0]} vetores e {len(indice)} uids. "
            "Reconstrua o índice."
        )
    posicao = {uid: i for i, uid in enumerate(indice["doc_uid"].astype(str))}
    faltam = [u for u in docs["doc_uid"] if u not in posicao]
    if faltam:
        raise ErroImportacao(
            f"{len(faltam)} documentos não têm vetor (ex.: {', '.join(faltam[:3])}). "
            "Rode build/construir_indice.py depois de reimportar a base."
        )
    ordem = [posicao[u] for u in docs["doc_uid"]]
    with open(pasta_camada / "camada.json", encoding="utf-8") as f:
        camada = json.load(f)
    return emb[ordem], camada


LINHAS_POR_PARTE = 100_000  # 100 mil x 384 x 2 bytes = 77 MB, abaixo do limite do GitHub


def gravar_embeddings(saida: Path, emb: np.ndarray) -> list[str]:
    """Grava os vetores em partes e devolve os nomes, relativos a `saida`."""
    pasta = saida / "embeddings"
    if pasta.exists():
        for velho in pasta.glob("*.npy"):
            velho.unlink()
    pasta.mkdir(parents=True, exist_ok=True)
    (saida / "embeddings.f16.npy").unlink(missing_ok=True)  # o formato de antes, num arquivo só
    nomes = []
    for k, a in enumerate(range(0, max(len(emb), 1), LINHAS_POR_PARTE)):
        nome = f"embeddings/parte_{k:03d}.f16.npy"
        np.save(saida / nome, emb[a:a + LINHAS_POR_PARTE])
        nomes.append(nome)
    return nomes


# ---------------------------------------------------------------------------
# Escrita
# ---------------------------------------------------------------------------

def construir(corpus: Path, saida: Path) -> dict:
    corpus, saida = Path(corpus), Path(saida)
    manifesto = ler_manifesto(corpus)
    usadas = {
        "tipologia": camada_ativa(manifesto, "tipologia"),
        "embeddings": camada_ativa(manifesto, "embeddings"),
    }
    pasta = corpus / "camadas"

    base = ler_base(corpus, manifesto)
    # Cotas e textos acertados, e o registro do DigitArq de cada documento (build/cotas.py).
    indice_digitarq = cotas.IndiceDigitArq.ler(corpus / "digitarq_referencias.tsv.gz")
    docreader = cotas.ler_docreader(corpus / "resgate_docreader.tsv.gz")
    base, acertos = cotas.ajustar(base, indice_digitarq, docreader)
    # Verbetes repetidos ficam nos dados, marcados; só a busca os ignora (corpus/duplicatas.ignore).
    ignorados = cotas.ler_ignorados(corpus / "duplicatas.ignore")
    base["duplicata_de"] = base["doc_uid"].map(lambda u: ignorados.get(u) or None
                                               if u in ignorados else None)
    acertos["duplicatas_ignoradas_na_busca"] = int(base["duplicata_de"].notna().sum())
    tipologia = _ler_parquet(pasta / usadas["tipologia"] / "tipologia.parquet", "camada de tipologia")
    docs = montar_documentos(base, tipologia)
    embeddings, camada_emb = alinhar_embeddings(pasta / usadas["embeddings"], docs)
    saida.mkdir(parents=True, exist_ok=True)
    lexico = construir_lexico(docs, saida)
    docs.to_parquet(saida / "documentos.parquet", index=False)
    for velho in ("pessoas.parquet", "doc_pessoa.parquet", "pdf_extra.parquet"):
        (saida / velho).unlink(missing_ok=True)  # artefatos de versões antigas
    # uid antigo -> uid atual, de todas as coleções (build/importar_colecao.py).
    apelidos = {}
    for colecao in manifesto.get("colecoes", {}):
        arq = corpus / "colecoes" / colecao / "apelidos.json"
        if arq.exists():
            with open(arq, encoding="utf-8") as f:
                apelidos.update(json.load(f))
    apelidos = {velho: novo for velho, novo in sorted(apelidos.items())
                if novo in set(docs["doc_uid"])}
    with open(saida / "apelidos.json", "w", encoding="utf-8") as f:
        json.dump(apelidos, f, ensure_ascii=False, indent=0)
    partes = gravar_embeddings(saida, embeddings.astype(np.float16))

    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    artefatos = ["documentos.parquet", "apelidos.json", *partes, *mod_lexico.arquivos(lexico["campos"])]
    app_manifesto = {
        "versao_artefatos": VERSAO_ARTEFATOS,
        "gerado_em": agora,
        "processo": {"script": "build/construir_app.py", "versao_script": VERSAO_SCRIPT,
                     "commit": commit_atual()},
        "corpus": {"versao_corpus": manifesto.get("versao_corpus"),
                   "gerado_em": manifesto.get("gerado_em"),
                   "colecoes": sorted(manifesto.get("colecoes", {})),
                   "camadas": {t: n for t, n in usadas.items() if n},
                   "manifesto": manifesto},
        "modelo_embeddings": {
            "nome": camada_emb.get("modelo"), "dimensao": camada_emb.get("dimensao"),
            "prefixo_consulta": camada_emb.get("prefixo_consulta"),
            "normalizado_l2": camada_emb.get("normalizado_l2"),
        },
        "lexico": {"versao": lexico["versao"], "pesos": lexico["pesos"],
                   "campos": lexico["campos"], "k1": lexico["k1"], "b": lexico["b"]},
        # Revisão e SHA-256 dos modelos que o app baixa em execução (ahu/consulta_onnx.py).
        "modelos": consulta_onnx.manifesto_modelos(),
        "acertos": acertos,
        "contagens": {
            "documentos": int(len(docs)),
            "colecoes": {str(k): int(v) for k, v in docs["colecao"].value_counts().items()},
        },
        # O app confere esta lista de uids, nesta ordem, contra documentos.parquet.
        "doc_uids_sha256": _sha256_texto("\n".join(docs["doc_uid"].astype(str))),
        "artefatos": {nome: sha256_arquivo(saida / nome) for nome in artefatos},
    }
    with open(saida / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(app_manifesto, f, ensure_ascii=False, indent=2)

    return {
        "documentos": len(docs),
        "colecoes": app_manifesto["contagens"]["colecoes"],
        "camadas": {t: n for t, n in usadas.items() if n},
        "dimensao": int(embeddings.shape[1]),
    }


def _sha256_texto(texto: str) -> str:
    import hashlib

    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", default=str(RAIZ / "corpus"))
    ap.add_argument("--saida", default=str(RAIZ / "app_dados"))
    args = ap.parse_args()
    try:
        r = construir(Path(args.corpus), Path(args.saida))
    except ErroImportacao as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 1
    print(f"{r['documentos']} documentos, embeddings de {r['dimensao']} dimensões.")
    print("Coleções: " + ", ".join(f"{k}={v}" for k, v in r["colecoes"].items()))
    print("Camadas: " + ", ".join(f"{k}={v}" for k, v in r["camadas"].items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
