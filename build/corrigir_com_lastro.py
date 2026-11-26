"""corrigir_com_lastro.py — desfaz no corpus os erros de leitura que a auditoria do lastro achou.

Entrada : o padrão ouro da auditoria de 21/11/2026 (`padrao_ouro.parquet`, gerado por
          `auditoria/auditar.py`), que pareia cada documento do banco com o seu verbete nos PDFs
          do ACTD e diz quem confirma o texto (lastro, banco, MAPE).
Saídas  : corpus/colecoes/<colecao>/documentos.parquet   corrigido no lugar
          corpus/colecoes/<colecao>/correcoes_lastro.parquet   uma linha por campo trocado, com
                                                               o valor antigo e o novo
          --revisar CAMINHO.csv (opcional)   os casos que ficam para olho humano

O que muda, e só com prova:

* **Resumo.** Quando o verbete é confirmado (`tripla`, `dupla` ou `lastro`) e o resumo do banco
  difere do da fonte sem acento e sem pontuação, o resumo passa a ser o do verbete. São os erros de
  leitura do PDF: rodapé colado no fim (`Nº de inventário no catálogo: 9084`), começo que foi parar
  na data, data colada no começo, resumo cortado. O texto da fonte não é reescrito: ele volta a ser
  o que está impresso, com os erros que a fonte tiver (que o app marca com [sic]).
* **Data.** Só quando o começo do resumo foi parar na data e a data do verbete é um começo do
  campo do banco (o corte é a única mudança), ou quando o banco não tinha data e o resumo antigo
  começava pela data do verbete.
* **Tipologia extraída.** Se o resumo mudou e a tipologia antiga não é o começo dele, ela passa a
  ser a palavra em maiúsculas que abre o resumo novo.
* **Notas da fonte (`notas_fonte`, coluna nova).** O rodapé de cada verbete confirmado (Anexo,
  Obs., Nota, Nº de inventário, "Anexa ao n.º"), que a leitura antiga deixava de fora ou, nos
  erros acima, colava no resumo. Nada do que a fonte diz se perde quando o resumo é limpo.
* **Cota (`new_code`).** Quando o fim da cota trouxe texto do verbete seguinte ou uma nota, e a
  cota do verbete no lastro é a mesma que sobra depois do corte.

O que não muda: os casos `revisar` (nenhuma fonte confirma a outra, ou a leitura do PDF ficou em
dúvida), os documentos sem verbete no lastro e os do gov.br (cujo resumo já foi achado na página).

Uso:
    python build/corrigir_com_lastro.py --ouro padrao_ouro.parquet [--revisar revisar.csv]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from build.cotas import limpar_new_code  # noqa: E402
from build.importar_base import atualizar_manifesto, sha256_arquivo  # noqa: E402
from build.importar_mape import texto_comparavel  # noqa: E402

CONFIRMADOS = {"tripla", "dupla", "lastro"}
RODAPE = ["anexo", "obs", "nota", "inventario", "remissao"]
_MAIUSC = "A-ZÁÉÍÓÚÂÊÔÃÕÇÀÜ"
_ESPECIE = re.compile(rf"^\[?([{_MAIUSC}][{_MAIUSC}\-]+(?:\s+(?:[{_MAIUSC}][{_MAIUSC}\-]+|D[AEO]S?|E))*)")
_NUMERO = re.compile(r"^\s*(\d+[A-Za-z]?\.)\s*(.*)$", re.S)
_ANO = re.compile(r"\b(1[4-8]\d\d)\b")
_COTA = re.compile(
    r"^(AHU_(?:ACL_)?CU_[\w\-]+,\s*[Cc]x\.\s*[\w\-]+,\s*(?:D\.|pasta)\s*\d[\d.]*[a-z]?"
    r"(?:\s*[-–]\s*\d[\d.]*[a-z]?)?\.?)(.*)$",
    re.S,
)


def _vazio(v) -> bool:
    return v is None or v is pd.NA or (isinstance(v, float) and pd.isna(v)) or not str(v).strip()


def espacos(texto: str) -> str:
    return re.sub(r"\s+", " ", str(texto)).strip()


def especie(resumo) -> str | None:
    """A palavra (ou palavras) em maiúsculas que abre o resumo: `CARTA PATENTE`, `OFÍCIO`."""
    m = _ESPECIE.match(str(resumo or "").strip())
    return m.group(1).strip() if m else None


def notas(o) -> str | None:
    """O rodapé do verbete numa linha só: `Anexo: 1 doc. | Obs.: m. est.`."""
    partes = [espacos(o[c]) for c in RODAPE if c in o and not _vazio(o[c])]
    return " | ".join(partes) or None


def chave_cota(texto) -> tuple | None:
    """Série, caixa e documento, só os números e a série: compara cotas escritas de jeitos diferentes."""
    m = re.search(r"CU_?([\w\-]+?),\s*[Cc]x\.?\s*([\w\-]+),\s*(?:D\.|DOC\.?|pasta)\s*([\d.]+)",
                  str(texto or ""), re.I)
    if not m:
        return None
    serie = m.group(1).upper().lstrip("0")
    return serie, m.group(2).upper().lstrip("0"), m.group(3).replace(".", "").lstrip("0")


def cortar_cota(new_code) -> str | None:
    """A cota sem o texto que grudou depois dela (verbete seguinte, nota). None se não há o que cortar."""
    texto = limpar_new_code(new_code)
    if not isinstance(texto, str):
        return None
    m = _COTA.match(texto.strip())
    if not m:
        return None
    resto = m.group(2).strip()
    if len(resto) < 15 or not re.search(r"[A-Za-zÀ-ú]{4,}", resto):
        return None
    return m.group(1).strip()


def nova_data(antiga, data_lastro, classe_resumo, resumo_antigo) -> str | None:
    """A data corrigida, ou None se não há prova bastante para mexer."""
    if _vazio(data_lastro) or _vazio(antiga):
        return None
    m = _NUMERO.match(str(antiga))
    numero, resto = (m.group(1), m.group(2)) if m else ("", str(antiga))
    alvo = texto_comparavel(data_lastro)
    if not alvo:
        return None
    if classe_resumo in {"sem_inicio_que_foi_para_a_data", "resumo_na_data"}:
        if texto_comparavel(resto).startswith(alvo) and texto_comparavel(resto) != alvo:
            return espacos(f"{numero} {data_lastro}")
    if classe_resumo == "data_no_resumo" and not texto_comparavel(resto):
        if texto_comparavel(resumo_antigo).startswith(alvo):
            return espacos(f"{numero} {data_lastro}")
    return None


def corrigir(base: pd.DataFrame, ouro: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devolve a base corrigida e a tabela de correções (doc_uid, campo, antes, depois, motivo)."""
    ouro = ouro[(ouro["fonte"] == "actd") & ouro["doc_uid"].notna()]
    ouro = ouro[~ouro["doc_uid"].duplicated(keep=False)]
    ouro = ouro[ouro["confirmacao"].isin(CONFIRMADOS)].set_index("doc_uid")
    base = base.copy()
    if "notas_fonte" not in base.columns:
        base["notas_fonte"] = pd.Series([None] * len(base), dtype=object)
    pos = {u: i for i, u in enumerate(base["doc_uid"])}
    trocas = []

    def trocar(i, campo, novo, motivo, uid, o):
        antes = base.at[i, campo]
        if _vazio(antes) and _vazio(novo):
            return
        if not _vazio(antes) and not _vazio(novo) and str(antes) == str(novo):
            return
        base.at[i, campo] = novo
        trocas.append({"doc_uid": uid, "campo": campo, "antes": None if _vazio(antes) else str(antes),
                       "depois": None if _vazio(novo) else str(novo), "motivo": motivo,
                       "id_lastro": o["id_lastro"], "confirmacao": o["confirmacao"]})

    for uid, o in ouro.iterrows():
        i = pos.get(uid)
        if i is None:
            continue
        classe = o["banco_resumo"] if isinstance(o["banco_resumo"], str) else "igual"
        resumo_antigo = base.at[i, "description"]
        resumo = o["resumo"]
        if not _vazio(resumo) and texto_comparavel(resumo) != texto_comparavel(resumo_antigo):
            novo = espacos(resumo)
            trocar(i, "description", novo, f"resumo:{classe}", uid, o)
            tip = base.at[i, "extracted_typology"]
            esp = especie(novo)
            if esp and (_vazio(tip) or not novo.startswith(str(tip).strip().lstrip("["))):
                trocar(i, "extracted_typology", esp, "tipologia:do_resumo_corrigido", uid, o)
        data = nova_data(base.at[i, "document_id_and_date"], o["data"], classe, resumo_antigo)
        if data:
            trocar(i, "document_id_and_date", data, f"data:{classe}", uid, o)
            if _vazio(base.at[i, "ano_isolado"]):
                # O ano vem da data do verbete, sem o número do documento que abre o campo
                # (`1447. [post. 1784]` daria 1447).
                ano = _ANO.search(str(o["data"]))
                if ano:
                    trocar(i, "ano_isolado", int(ano.group(1)), "ano:da_data_corrigida", uid, o)
        base.at[i, "notas_fonte"] = notas(o)
        cota = cortar_cota(base.at[i, "new_code"])
        if cota and chave_cota(cota) is not None and chave_cota(cota) == chave_cota(o["cota_texto"]):
            trocar(i, "new_code", cota, "cota:texto_colado_depois", uid, o)

    base["ano_isolado"] = base["ano_isolado"].astype("Int64")
    tabela = pd.DataFrame(trocas, columns=["doc_uid", "campo", "antes", "depois", "motivo",
                                           "id_lastro", "confirmacao"])
    return base, tabela


def para_revisar(base: pd.DataFrame, ouro: pd.DataFrame) -> pd.DataFrame:
    """Os casos `revisar`, com os três textos lado a lado e o link para a página do PDF."""
    r = ouro[ouro["confirmacao"] == "revisar"].copy()
    colunas = ["doc_uid", "folder", "new_code", "description", "document_id_and_date", "url_actd"]
    r = r.merge(base[[c for c in colunas if c in base.columns]], on="doc_uid", how="left")
    pagina = r["pagina_inicio"].astype("Int64").astype(str)
    r["link_pdf"] = [f"{u}#page={p}" if isinstance(u, str) and p != "<NA>" else None
                     for u, p in zip(r["url_actd"], pagina)]
    return r.rename(columns={"marcas": "motivo", "resumo": "resumo_lastro", "data": "data_lastro",
                             "description": "resumo_banco", "document_id_and_date": "data_banco",
                             "mape_resumo": "resumo_mape_ou_classe"})[
        ["folder", "new_code", "cota_texto", "motivo", "fonte", "arquivo", "pagina_inicio",
         "link_pdf", "data_lastro", "data_banco", "resumo_lastro", "resumo_banco", "doc_uid"]
    ].sort_values(["folder", "arquivo", "pagina_inicio"], na_position="last")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ouro", required=True, type=Path)
    ap.add_argument("--colecao", default="ahu-brasil")
    ap.add_argument("--corpus", default=RAIZ / "corpus", type=Path)
    ap.add_argument("--revisar", type=Path)
    a = ap.parse_args(argv)

    pasta = a.corpus / "colecoes" / a.colecao
    camada = json.loads((pasta / "camada.json").read_text("utf-8"))
    if "correcoes_lastro" in camada:
        print("A coleção já foi corrigida com o lastro (camada.json). Reimporte a base antes.")
        return 1
    base = pd.read_parquet(pasta / "documentos.parquet")
    ouro = pd.read_parquet(a.ouro)
    nova, tabela = corrigir(base, ouro)
    nova.to_parquet(pasta / "documentos.parquet", index=False)
    tabela.to_parquet(pasta / "correcoes_lastro.parquet", index=False)

    camada["correcoes_lastro"] = {
        "script": "build/corrigir_com_lastro.py",
        "padrao_ouro_sha256": sha256_arquivo(a.ouro),
        "documentos_corrigidos": int(tabela["doc_uid"].nunique()),
        "documentos_com_notas_fonte": int(nova["notas_fonte"].notna().sum()),
        "por_campo": {k: int(v) for k, v in tabela["campo"].value_counts().items()},
        "por_motivo": {k: int(v) for k, v in tabela["motivo"].value_counts().items()},
    }
    (pasta / "camada.json").write_text(json.dumps(camada, ensure_ascii=False, indent=2) + "\n", "utf-8")
    atualizar_manifesto(a.corpus, a.colecao, pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds"))

    print(json.dumps(camada["correcoes_lastro"], ensure_ascii=False, indent=2))
    if a.revisar:
        para_revisar(nova, ouro).to_csv(a.revisar, index=False)
        print(f"revisar: {a.revisar}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
