"""importar_base_mape.py — a base aberta do catálogo: os verbetes do dataset do MAPE.

Fonte: *MAPE: A Dataset of Correspondence from the Portuguese Empire* (Mapping the Atlantic
Portuguese Empire), de Agata Błoch, Demival Vasques Filho, Michał Bojanowski, Clodomir Santana,
Saddam Hussain, Apolinary Rzońca e Artur Podsiadły. Zenodo, versão 6 (20/11/2026),
doi:10.5281/zenodo.24403753, licença CC BY 4.0. O arquivo **não** vai no repositório nem no
pacote do catálogo: quem reproduz baixa o CSV do Zenodo do MAPE.

O script lê o CSV e escreve, em `corpus/`, uma coleção no formato comum do catálogo (o mesmo da
base do ACTD), mais duas camadas:

* `colecoes/mape-v6/documentos.parquet`: um verbete do MAPE por linha, só das séries do Brasil e
  do Rio da Prata (as da cifra de `ahu/conversor.py`). `doc_uid` = `mape-v6:<doc_id>`;
* `camadas/tipologia_v1/`: a tipologia, tirada das palavras em maiúsculas que abrem o resumo
  (a mesma regra do catálogo; o `doc_type` do MAPE reduz tudo a formas genéricas e não é usado);
* `camadas/mape_en_v6/`: a tradução inglesa do MAPE, sem alterações.

O que fica de fora, de propósito: remetente, destinatário e tópicos (`sender_name`,
`receiver_name`, `llm_suggested_topic` e os *clusters*), gerados por modelo de linguagem; e o
`doc_type`.

Cotas e datas:

* o **código de referência** é o do MAPE, que é o do DigitArq, com os zeros à esquerda
  (`…/0101/7581` vira `…/0101/07581`). Os intervalos (`…/0001/00009.00019`, um documento e os seus
  anexos) ficam como estão; a cota do Resgate sai com o intervalo (`D. 9-19`);
* a **data** é montada de `year`, `month` e `day`. Nos intervalos de data o MAPE dá o ano final, e
  não o inicial como o ACTD. O MAPE não traz o lugar;
* a **cota antiga** não vem do MAPE: o módulo `compat/` a preenche pela tabela de concordância.

Os links ao Projeto Resgate e ao DigitArq vêm depois, do módulo `compat/`, na construção do app.

Uso: python build/importar_base_mape.py --entrada dados/mape_dataset_version_6.csv [--corpus corpus]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from ahu import conversor  # noqa: E402
from build.importar_base import (  # noqa: E402
    CAMPOS_BASE,
    ErroImportacao,
    atualizar_manifesto,
    commit_atual,
    sha256_arquivo,
)
from build.importar_camadas import gravar_camada, importar_camadas, registrar_no_manifesto  # noqa: E402
from build.importar_mape import CAMADA_MAPE, COLUNA_EN, COLUNA_PT, FONTE, ler_mape  # noqa: E402

VERSAO_SCRIPT = "1.0.0"
COLECAO = "mape-v6"
# SHA-256 do mape_dataset_version_6.csv publicado no Zenodo (doi:10.5281/zenodo.24403753).
SHA256_V6 = "571d8c5a5f0d47c325bc9ed6a1f7c75ab3642ede764ab6992f0fe51442324beb"
MAX_INTERVALO = 50
MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto",
         "Setembro", "Outubro", "Novembro", "Dezembro"]

_CODIGO = re.compile(r"^PT/AHU/CU/([\d-]+)/(\d+)/(\d+)((?:\.[0-9A-Za-z]+)*)$")
_PARTE_NUMERICA = re.compile(r"^\d+$")
# A espécie documental que abre o resumo: palavras em maiúsculas, até a primeira palavra em
# minúscula, preposição ou pontuação ("REQUERIMENTO do capitão…", "CARTA PATENTE do rei…").
_TIPOLOGIA = re.compile(
    r"^\s*([A-ZÀ-Ý][A-ZÀ-Ý\s\-]+?)"
    r"(?=\s+(?:d[aeo]s?|ao?s?|à|em|que|sobre|para|por|com)\b|[,.(\[:;]|\s+[A-ZÀ-Ý][a-zà-ý]|$)")


def normalizar_codigo(codigo) -> str | None:
    """O código do MAPE com os zeros à esquerda: caixa com 4 algarismos, documento com 5; as
    partes depois do ponto (fim do intervalo) também com 5 quando são números."""
    if not isinstance(codigo, str):
        return None
    m = _CODIGO.match(codigo.strip())
    if not m:
        return None
    serie, caixa, doc, resto = m.groups()
    partes = [p if not _PARTE_NUMERICA.match(p) else f"{int(p):05d}"
              for p in resto.split(".") if p]
    return f"PT/AHU/CU/{serie}/{int(caixa):04d}/{int(doc):05d}" + "".join(f".{p}" for p in partes)


def intervalo(codigo: str) -> tuple[int, int | None, bool]:
    """(primeiro número, último número ou None, se o intervalo é anômalo)."""
    fim_doc = codigo.rsplit("/", 1)[1]
    partes = fim_doc.split(".")
    ini = int(partes[0])
    if len(partes) == 1:
        return ini, None, False
    if len(partes) == 2 and _PARTE_NUMERICA.match(partes[1]):
        fim = int(partes[1])
        if 0 < fim - ini <= MAX_INTERVALO:
            return ini, fim, False
    return ini, None, True


def cota_do_codigo(codigo: str) -> conversor.Cota | None:
    cota = conversor.reconhecer(codigo)
    if cota is None or cota.serie is None:
        return None
    _, fim, _ = intervalo(codigo)
    if fim is not None:
        cota = replace(cota, documento_fim=fim)
    return cota


def tipologia(texto) -> str | None:
    if not isinstance(texto, str):
        return None
    m = _TIPOLOGIA.match(texto)
    return re.sub(r"\s+", " ", m.group(1)).strip(" -") if m else None


def data_texto(ano, mes, dia) -> str | None:
    """`1821, Outubro, 17`, como o ACTD escreve as datas; só o que o MAPE trouxer."""
    if not isinstance(ano, str) or not ano[:4].isdigit():
        return None
    partes = [ano[:4]]
    try:
        m = int(float(mes))
        partes.append(MESES[m - 1])
        d = int(float(dia))
        partes.append(str(d))
    except (TypeError, ValueError, IndexError):
        pass
    return ", ".join(partes)


def montar(mape: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Os verbetes do Brasil e do Prata no formato comum, e as contagens da conversão."""
    contagem = {"mape_registros": int(len(mape))}
    codigos = mape["reference_code"].map(normalizar_codigo)
    cotas = [cota_do_codigo(c) if c else None for c in codigos]
    na_cifra = pd.Series([c is not None and c.codigo_serie in conversor.POR_CODIGO for c in cotas],
                         index=mape.index)
    contagem["fora_da_cifra"] = int((~na_cifra).sum())
    m = mape[na_cifra].copy()
    m["reference_code"] = codigos[na_cifra]
    cotas = [c for c, ok in zip(cotas, na_cifra) if ok]
    anomalos = [intervalo(c)[2] for c in m["reference_code"]]
    docs = pd.DataFrame({
        "doc_uid": [f"{COLECAO}:{int(i)}" for i in m["doc_id"]],
        "colecao": COLECAO,
        "folder": [conversor.POR_CODIGO[c.codigo_serie].nome.split(",")[0] for c in cotas],
        "description": m[COLUNA_PT].values,
        "old_code": None,
        "new_code": [conversor.para_resgate(c) for c in cotas],
        "reference_code": m["reference_code"].values,
        "document_id_and_date": [data_texto(a, me, d) for a, me, d in
                                 zip(m["year"], m["month"], m["day"])],
        "ano_isolado": pd.array([int(a[:4]) if isinstance(a, str) and a[:4].isdigit() else None
                                 for a in m["year"]], dtype="Int64"),
        "extracted_typology": m[COLUNA_PT].map(tipologia).values,
        "mape_doc_id": m["doc_id"].astype("int64").values,
        "qc": ["intervalo_anomalo" if a else None for a in anomalos],
    })
    if not docs["doc_uid"].is_unique:
        raise ErroImportacao("doc_id repetido no CSV do MAPE.")
    contagem.update({
        "documentos": int(len(docs)),
        "intervalos": int(docs["reference_code"].str.contains(r"/\d+\.", regex=True).sum()),
        "intervalos_anomalos": int(sum(anomalos)),
        "sem_tipologia": int(docs["extracted_typology"].isna().sum()),
    })
    return docs, contagem


def traducao(docs: pd.DataFrame, mape: pd.DataFrame) -> pd.DataFrame:
    """A camada mape_en_v6 desta base: cada verbete tem a sua própria tradução, sem pareamento."""
    en = mape.set_index("doc_id")[COLUNA_EN]
    resumo_en = docs["mape_doc_id"].map(en)
    return pd.DataFrame({
        "doc_uid": docs["doc_uid"],
        "mape_doc_id": docs["mape_doc_id"],
        "mape_reference_code": docs["reference_code"],
        "semelhanca": 1.0,
        "ligado": resumo_en.map(lambda t: isinstance(t, str) and bool(t.strip())),
        "resumo_en": resumo_en.where(resumo_en.map(lambda t: isinstance(t, str)), None),
    })


def importar(entrada: Path, corpus: Path, exigir_v6: bool = False) -> dict:
    entrada, corpus = Path(entrada), Path(corpus)
    sha = sha256_arquivo(entrada) if entrada.exists() else None
    if exigir_v6 and sha != SHA256_V6:
        raise ErroImportacao(f"O arquivo {entrada.name} não é o mape_dataset_version_6.csv "
                             f"(SHA-256 {str(sha)[:12]}…). Rode sem --exigir-v6 para usar outra versão.")
    mape = ler_mape(entrada)
    docs, contagem = montar(mape)
    faltam = [c for c in CAMPOS_BASE if c not in docs.columns]
    if faltam:
        raise ErroImportacao(f"Faltam colunas do formato comum: {faltam}")

    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    pasta = corpus / "colecoes" / COLECAO
    pasta.mkdir(parents=True, exist_ok=True)
    docs.to_parquet(pasta / "documentos.parquet", index=False)
    with open(pasta / "registro_ids.json", "w", encoding="utf-8") as f:
        json.dump({"origem": "doc_uid = mape-v6:<doc_id do MAPE>", "documentos": len(docs)},
                  f, ensure_ascii=False, indent=2)
    with open(pasta / "apelidos.json", "w", encoding="utf-8") as f:
        json.dump({}, f)
    camada = {
        "nome": f"base_{COLECAO}", "tipo": "base", "versao": "1", "colecao": COLECAO,
        "base": "mape",
        "processo": {"script": "build/importar_base_mape.py", "versao_script": VERSAO_SCRIPT,
                     "commit": commit_atual()},
        "entrada": {"arquivo": entrada.name, "sha256": sha, "versao_6": sha == SHA256_V6},
        "data": agora, "documentos": len(docs), "contagem": contagem,
        "fonte": FONTE,
        "fora_da_base": ["sender_name", "receiver_name", "llm_suggested_topic",
                         "parent_cluster_title", "child_cluster_title",
                         "parent_child_sub_cluster_title", "doc_type"],
        "origem": "Verbetes do dataset do MAPE (texto do DigitArq/AHU), CC BY 4.0. Cotas antigas "
                  "e links de acesso: módulo de compatibilidade do Catálogo AHU-Brasil (compat/).",
    }
    with open(pasta / "camada.json", "w", encoding="utf-8") as f:
        json.dump(camada, f, ensure_ascii=False, indent=2)
    atualizar_manifesto(corpus, COLECAO, agora)

    # Tipologia (a mesma camada e a mesma regra de canônica da base do ACTD).
    importar_camadas(pasta / "documentos.parquet", corpus, COLECAO)

    # Tradução inglesa do próprio MAPE.
    pasta_en = corpus / "camadas" / CAMADA_MAPE
    tabela_en = traducao(docs, mape)
    camada_en = gravar_camada(pasta_en, "mape.parquet", tabela_en, {
        "nome": CAMADA_MAPE, "tipo": "traducao_en", "versao": "6", "colecoes": [COLECAO],
        "fonte": FONTE,
        "regra": "Base MAPE: cada verbete traz a própria tradução do MAPE, sem pareamento e sem "
                 "alterações (inclusive os erros da tradução automática).",
        "documentos": int(len(tabela_en)), "ligados": int(tabela_en["ligado"].sum()),
        "processo": {"script": "build/importar_base_mape.py", "versao_script": VERSAO_SCRIPT,
                     "commit": commit_atual()},
        "entrada": {"arquivo": entrada.name, "sha256": sha},
    })
    registrar_no_manifesto(corpus, pasta_en, camada_en, ("mape.parquet", "camada.json"))
    return contagem


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--entrada", required=True, help="o mape_dataset_version_6.csv")
    ap.add_argument("--corpus", default=str(RAIZ / "corpus"))
    ap.add_argument("--exigir-v6", action="store_true",
                    help="para se o arquivo não for exatamente o CSV da versão 6")
    a = ap.parse_args()
    try:
        r = importar(Path(a.entrada), Path(a.corpus), a.exigir_v6)
    except ErroImportacao as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 1
    print(", ".join(f"{k}={v}" for k, v in r.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
