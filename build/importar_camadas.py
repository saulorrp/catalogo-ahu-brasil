"""importar_camadas.py — camada `tipologia_v1`: a tipologia do catálogo, normalizada.

Entrada : uma base já com doc_uid (corpus/colecoes/<colecao>/documentos.parquet) ou a lista JSON
          que o build/importar_base.py importou
Saídas  : corpus/camadas/tipologia_v1/
              tipologia.parquet    doc_uid, tipologia_bruta, tipologia, tipologia_chave,
                                   typology_status, tipologia_corrigida
              camada.json          regra de normalização, tabela de correções aplicada, contagens

Regras:
  * uma linha por `doc_uid`, na ordem da base;
  * as tipologias vêm dos dados. O script só normaliza a forma (maiúsculas, espaços, pontuação) e
    aplica a tabela de correções de `corpus/correcoes_tipologia.json`, que o autor edita à mão.
    Nenhum vocabulário de tipologias está embutido no código;
  * sem `typology_status` na entrada, é canônica a tipologia que aparece em pelo menos
    MINIMO_CANONICA documentos da coleção (regra dos dados, não lista do código).

Uso:
    python build/importar_camadas.py --colecao ahu-brasil \
        --entrada corpus/colecoes/ahu-brasil/documentos.parquet
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from build.importar_base import (  # noqa: E402
    ErroImportacao,
    commit_atual,
    hash_conteudo,
    normalizar,
    sha256_arquivo,
)

VERSAO_SCRIPT = "1.0.0"
CAMADA_TIPOLOGIA = "tipologia_v1"
MINIMO_CANONICA = 5

REGRA_TIPOLOGIA = (
    "maiúsculas, NFC, espaços colapsados, pontuação e aspas das pontas removidas; "
    "depois a tabela de correções de corpus/correcoes_tipologia.json, casada pela forma normalizada "
    "com acentos (para que a tabela possa corrigir acento trocado). "
    "Valor vazio -> tipologia nula e typology_status falso."
)

# Tabela inicial de correções: só erros de extração inequívocos. O autor acrescenta os que faltarem.
CORRECOES_INICIAIS = {
    "_LEIA-ME": (
        "Correções de tipologia da camada tipologia_v1. Chave = tipologia como vem do catálogo, "
        "em maiúsculas e com os acentos tal como estão (é por isso que acento trocado pode ser "
        "corrigido aqui); valor = forma correta (string vazia = tipologia desconhecida). "
        "Acrescente aqui qualquer erro de extração e rode build/importar_camadas.py de novo. "
        "Nenhuma tipologia é definida no código: esta tabela e os dados mandam."
    ),
    "COSIJLTA": "CONSULTA",
    "OFICÍO": "OFÍCIO",
    "RELÁTORIO": "RELATÓRIO",
    "UNKNOWN": "",
}

RE_PONTAS = re.compile(r"^[\s\"'“”«»\[\](){}.,;:–—-]+|[\s\"'“”«»\[\](){}.,;:–—-]+$")


# ---------------------------------------------------------------------------
# Tipologia
# ---------------------------------------------------------------------------

def normalizar_tipologia(bruto) -> str:
    """Só a forma: maiúsculas, espaços colapsados, pontuação das pontas fora. Não traduz nada."""
    if bruto is None:
        return ""
    t = unicodedata.normalize("NFC", str(bruto))
    t = RE_PONTAS.sub("", t)
    return re.sub(r"\s+", " ", t).strip().upper()


def chave_tipologia(tipologia: str) -> str:
    """Chave de filtro e de URL: sem acentos, maiúscula (usa a normalização da base)."""
    return normalizar(tipologia).upper()


def carregar_correcoes(arquivo: Path) -> dict[str, str]:
    """Lê (ou cria com os padrões) a tabela de correções. Devolve só os pares úteis."""
    if not arquivo.exists():
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        with open(arquivo, "w", encoding="utf-8") as f:
            json.dump(CORRECOES_INICIAIS, f, ensure_ascii=False, indent=2)
    with open(arquivo, encoding="utf-8") as f:
        tabela = json.load(f)
    if not isinstance(tabela, dict):
        raise ErroImportacao(f"{arquivo.name} deve ser um objeto JSON (chave = tipologia, valor = correção).")
    correcoes = {}
    for chave, valor in tabela.items():
        if chave.startswith("_"):
            continue
        if not isinstance(valor, str):
            raise ErroImportacao(f"{arquivo.name}: a correção de {chave!r} deve ser uma string.")
        correcoes[normalizar_tipologia(chave)] = normalizar_tipologia(valor)
    return correcoes


def vocabulario_canonico(docs: list[dict]) -> set[str]:
    """As tipologias que o catálogo marca como canônicas em algum documento.

    Sai dos dados, nunca do código. Serve para que uma correção de forma
    ('OFICÍO' -> 'OFÍCIO') herde o status da forma certa, em vez de ficar como a revisar.
    """
    return {
        normalizar_tipologia(d.get("extracted_typology"))
        for d in docs
        if d.get("typology_status") is True and normalizar_tipologia(d.get("extracted_typology"))
    }


def montar_tipologia(docs: list[dict], uids: list[str], correcoes: dict[str, str]) -> pd.DataFrame:
    canonicas = vocabulario_canonico(docs)
    linhas = []
    for doc, uid in zip(docs, uids):
        bruto = doc.get("extracted_typology")
        forma = normalizar_tipologia(bruto)
        corrigida = forma in correcoes
        tipologia = correcoes[forma] if corrigida else forma
        status = doc.get("typology_status")
        if not isinstance(status, bool):
            raise ErroImportacao(
                f"{uid}: typology_status deveria ser verdadeiro ou falso, veio {status!r}."
            )
        linhas.append({
            "doc_uid": uid,
            "tipologia_bruta": None if bruto is None else str(bruto),
            "tipologia": tipologia or None,
            "tipologia_chave": chave_tipologia(tipologia) or None,
            "typology_status": bool(tipologia) and (status or tipologia in canonicas),
            "tipologia_corrigida": corrigida,
        })
    df = pd.DataFrame(linhas, columns=[
        "doc_uid", "tipologia_bruta", "tipologia", "tipologia_chave",
        "typology_status", "tipologia_corrigida",
    ])
    df["typology_status"] = df["typology_status"].astype(bool)
    df["tipologia_corrigida"] = df["tipologia_corrigida"].astype(bool)
    return df


def uids_da_entrada(docs: list[dict], pasta_colecao: Path) -> list[str]:
    """Casa cada documento da entrada com o seu doc_uid pelo hash de conteúdo do registro."""
    arq_registro = pasta_colecao / "registro_ids.json"
    arq_base = pasta_colecao / "documentos.parquet"
    for arq in (arq_registro, arq_base):
        if not arq.exists():
            raise ErroImportacao(f"{arq} não existe. Importe a coleção antes.")
    with open(arq_registro, encoding="utf-8") as f:
        registro = json.load(f)
    da_base = set(pd.read_parquet(arq_base, columns=["doc_uid"])["doc_uid"].astype(str))

    por_hash: dict[str, list[str]] = {}
    for r in registro.get("documentos", []):
        if r["doc_uid"] in da_base:
            por_hash.setdefault(r["hash_conteudo"], []).append(r["doc_uid"])

    uids: list[str] = []
    for i, doc in enumerate(docs):
        candidatos = por_hash.get(hash_conteudo(doc))
        if not candidatos:
            raise ErroImportacao(
                f"Documento {i} da entrada não está na base ({doc.get('reference_code')!r}). "
                "A entrada mudou desde a importação: rode build/importar_base.py de novo."
            )
        uids.append(candidatos.pop(0))

    if len(uids) != len(da_base):
        raise ErroImportacao(
            f"A entrada tem {len(uids)} documentos e a base {len(da_base)}. "
            "Rode build/importar_base.py de novo."
        )
    return uids


# ---------------------------------------------------------------------------
# Escrita das camadas e do manifesto
# ---------------------------------------------------------------------------

def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _contagens(df: pd.DataFrame, coluna: str) -> dict:
    serie = df[coluna].dropna()
    return {str(k): int(v) for k, v in serie.value_counts().sort_index().items()}


def mesclar_colecoes(pasta: Path, arquivo_dados: str, df: pd.DataFrame) -> pd.DataFrame:
    """Guarda as linhas das outras coleções que já estavam na camada.

    Cada execução cobre uma coleção. Sem isto, importar `teste-mini` apagaria `ahu-brasil` da camada.
    A ordem das linhas não importa: o `construir_app.py` junta tudo pela ordem da base.
    """
    arq = pasta / arquivo_dados
    if not arq.exists():
        return df
    anterior = pd.read_parquet(arq)
    de_outras = anterior[~anterior["doc_uid"].isin(set(df["doc_uid"]))]
    if de_outras.empty:
        return df
    return pd.concat([df, de_outras], ignore_index=True)


def colecoes_cobertas(pasta: Path, colecao: str) -> list[str]:
    """As coleções que a camada passa a cobrir: as de antes mais a desta execução."""
    anteriores = []
    arq = pasta / "camada.json"
    if arq.exists():
        with open(arq, encoding="utf-8") as f:
            anteriores = list(json.load(f).get("colecoes") or [])
    return sorted({*anteriores, colecao})


def gravar_camada(pasta: Path, arquivo_dados: str, df: pd.DataFrame, camada: dict) -> dict:
    pasta.mkdir(parents=True, exist_ok=True)
    df.to_parquet(pasta / arquivo_dados, index=False)
    camada = {
        **camada,
        "documentos": int(len(df)),
        "esquema": {c: str(t) for c, t in df.dtypes.items()},
        "data": _agora(),
    }
    with open(pasta / "camada.json", "w", encoding="utf-8") as f:
        json.dump(camada, f, ensure_ascii=False, indent=2)
    return camada


def registrar_no_manifesto(corpus: Path, pasta: Path, camada: dict, arquivos: tuple[str, ...]) -> None:
    arq = corpus / "manifest.json"
    manifesto = {"versao_corpus": "0.1.0", "colecoes": {}, "camadas": {}}
    if arq.exists():
        with open(arq, encoding="utf-8") as f:
            manifesto = json.load(f)
    manifesto.setdefault("camadas", {})[pasta.name] = {
        "tipo": camada["tipo"],
        "versao": camada["versao"],
        "documentos": camada["documentos"],
        "arquivos": {f"camadas/{pasta.name}/{n}": sha256_arquivo(pasta / n) for n in arquivos},
        "ativa": True,
    }
    manifesto["gerado_em"] = camada["data"]
    with open(arq, "w", encoding="utf-8") as f:
        json.dump(manifesto, f, ensure_ascii=False, indent=2)


def importar_camadas(entrada: Path, corpus: Path, colecao: str) -> dict:
    entrada, corpus = Path(entrada), Path(corpus)
    if not entrada.exists():
        raise ErroImportacao(f"Arquivo de entrada não encontrado: {entrada}")
    if entrada.suffix == ".parquet":
        tabela = pd.read_parquet(entrada)
        uids = tabela["doc_uid"].astype(str).tolist()
        docs = tabela.drop(columns=["doc_uid"]).astype(object).where(tabela.notna(), None
                                                                   ).to_dict("records")
    else:
        try:
            with open(entrada, encoding="utf-8") as f:
                docs = json.load(f)
        except json.JSONDecodeError as e:
            raise ErroImportacao(f"JSON inválido ou truncado em {entrada}: {e}") from e
        if not isinstance(docs, list):
            raise ErroImportacao("O catálogo de entrada deve ser uma lista de documentos.")
        uids = uids_da_entrada(docs, corpus / "colecoes" / colecao)
    # Sem `typology_status` no catálogo: é canônica a forma que se repete na coleção.
    if any(d.get("typology_status") is None for d in docs):
        frequencia: dict[str, int] = {}
        for d in docs:
            forma = normalizar_tipologia(d.get("extracted_typology"))
            if forma:
                frequencia[forma] = frequencia.get(forma, 0) + 1
        canonicas = {f for f, n in frequencia.items() if n >= MINIMO_CANONICA}
        for d in docs:
            if d.get("typology_status") is None:
                d["typology_status"] = normalizar_tipologia(d.get("extracted_typology")) in canonicas

    processo = {"script": "build/importar_camadas.py", "versao_script": VERSAO_SCRIPT,
                "commit": commit_atual()}
    arq_correcoes = corpus / "correcoes_tipologia.json"
    correcoes = carregar_correcoes(arq_correcoes)
    pasta = corpus / "camadas" / CAMADA_TIPOLOGIA
    df = mesclar_colecoes(pasta, "tipologia.parquet", montar_tipologia(docs, uids, correcoes))
    camada = gravar_camada(pasta, "tipologia.parquet", df, {
        "nome": CAMADA_TIPOLOGIA,
        "tipo": "tipologia",
        "versao": "1",
        "colecoes": colecoes_cobertas(pasta, colecao),
        "origem_do_campo": "a tipologia que abre cada verbete do catálogo do AHU",
        "regra_normalizacao": REGRA_TIPOLOGIA,
        "regra_status": "typology_status da entrada, se houver; senão, a forma aparecer em pelo "
                        f"menos {MINIMO_CANONICA} documentos da coleção. A tipologia corrigida "
                        "herda o status da forma certa.",
        "correcoes": {"arquivo": arq_correcoes.name, "tabela": correcoes,
                      "aplicadas": int(df["tipologia_corrigida"].sum())},
        "tipologias_distintas": int(df["tipologia"].nunique(dropna=True)),
        "canonicas": int(df["typology_status"].sum()),
        "a_revisar": int((~df["typology_status"]).sum()),
        "contagem_por_tipologia": _contagens(df, "tipologia"),
        "processo": processo,
        "entrada": {"arquivo": entrada.name, "sha256": sha256_arquivo(entrada)},
    })
    registrar_no_manifesto(corpus, pasta, camada, ("tipologia.parquet", "camada.json"))
    return {"documentos": len(uids), "camadas": {CAMADA_TIPOLOGIA: {
        "distintas": camada["tipologias_distintas"], "canonicas": camada["canonicas"],
        "a_revisar": camada["a_revisar"], "corrigidas": camada["correcoes"]["aplicadas"],
    }}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--entrada", required=True)
    ap.add_argument("--corpus", default=str(RAIZ / "corpus"))
    ap.add_argument("--colecao", required=True)
    args = ap.parse_args()
    try:
        r = importar_camadas(Path(args.entrada), Path(args.corpus), args.colecao)
    except ErroImportacao as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 1
    print(f"{r['documentos']} documentos.")
    for nome, info in r["camadas"].items():
        print(f"  {nome}: " + ", ".join(f"{k}={v}" for k, v in info.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
