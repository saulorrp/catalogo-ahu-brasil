"""aplicar_revisao_lastro.py — aplica as decisões dos casos `revisar` da auditoria do lastro.

O `corrigir_com_lastro.py` deixa de fora os casos em que nenhuma fonte confirmava a outra ou em
que a leitura do PDF ficou em dúvida (os `revisar` do padrão ouro). Eles foram decididos depois,
um a um, por três caminhos, e cada decisão diz de qual versão vem o texto: A (lastro, o PDF do
ACTD), B (banco, como estava) ou C (MAPE v6):

* **regra:** as versões e o bloco bruto do PDF bastavam para decidir (fontes iguais, corte entre
  data e resumo, começo do resumo que estava na data);
* **modelo:** um modelo de linguagem escolheu entre as versões existentes, sem escrever texto, e
  um conferidor automático só aceitou a escolha quando o texto está no bloco do PDF;
* **humano:** os casos que sobraram, decididos pelo autor numa página de escolha (CSV).

Entrada : --decisoes  JSONL com id_lastro, doc_uid, fonte_decisao, escolha_resumo, escolha_data,
                      resumo e data (o texto da versão escolhida)
          --humano    (opcional) CSV `;` exportado pela página de escolha, com doc_uid, P1_resumo,
                      P2_data, texto_escolhido e data_escolhida; vale para os `humano_pendente`
Saídas  : documentos.parquet da coleção, corrigido no lugar, e as trocas acrescentadas a
          correcoes_lastro.parquet (motivo `revisar:<fonte da decisão>`)

Só muda o que a decisão manda e só quando o texto escolhido difere do banco sem acento e sem
pontuação. B, `nenhum` e `incerto` deixam o banco como está. Uma data escolhida sem ano não
substitui uma data do banco que tem ano. Rodar de novo não refaz o que já foi aplicado: um
documento que já tem troca `revisar:` no registro é pulado, e assim as decisões do autor podem
entrar depois das outras.

Uso:
    python build/aplicar_revisao_lastro.py --decisoes decisoes_650.jsonl [--humano escolha.csv] \
        --corpus $ACTD/corpus
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

from build.corrigir_com_lastro import _vazio, espacos, especie  # noqa: E402
from build.importar_base import atualizar_manifesto  # noqa: E402
from build.importar_mape import texto_comparavel  # noqa: E402

TROCAM = {"A", "C"}
_NUMERO = re.compile(r"^\s*(\d+[A-Za-z]?(?:\s*[-–]\s*\d+[A-Za-z]?)?\.)\s*(.*)$", re.S)
_ANO = re.compile(r"\b(1[4-8]\d\d)\b")
COLUNAS_LOG = ["doc_uid", "campo", "antes", "depois", "motivo", "id_lastro", "confirmacao"]


def ler_decisoes(caminho: Path) -> list[dict]:
    with open(caminho, encoding="utf-8") as f:
        return [json.loads(linha) for linha in f if linha.strip()]


def ler_humano(caminho: Path) -> dict[str, dict]:
    """doc_uid -> decisão, a partir do CSV da página de escolha."""
    df = pd.read_csv(caminho, sep=";", dtype=str, encoding="utf-8-sig").fillna("")
    out = {}
    for r in df.to_dict("records"):
        uid = r.get("doc_uid", "").strip()
        if not uid:
            continue
        out[uid] = {
            "escolha_resumo": r.get("P1_resumo") or None,
            "escolha_data": r.get("P2_data") or None,
            "resumo": r.get("texto_escolhido") or None,
            "data": r.get("data_escolhida") or None,
            "observacao": r.get("P3_observacao") or None,
        }
    return out


def nova_data(antiga, escolhida) -> str | None:
    """`numero. data escolhida`, mantendo o número do banco; None se não há o que trocar."""
    if _vazio(escolhida):
        return None
    m = _NUMERO.match(str(antiga or ""))
    numero, resto = (m.group(1), m.group(2)) if m else ("", str(antiga or ""))
    if texto_comparavel(resto) == texto_comparavel(escolhida):
        return None
    if _ANO.search(resto) and not _ANO.search(str(escolhida)):
        return None
    return espacos(f"{numero} {escolhida}")


def aplicar(base: pd.DataFrame, decisoes: list[dict], humano: dict | None = None,
            ja_feitos: set | None = None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    base = base.copy()
    pos = {u: i for i, u in enumerate(base["doc_uid"])}
    humano = humano or {}
    ja_feitos = ja_feitos or set()
    trocas, contagem = [], {}

    def contar(k):
        contagem[k] = contagem.get(k, 0) + 1

    def trocar(i, campo, novo, motivo, d):
        antes = base.at[i, campo]
        if not _vazio(antes) and str(antes) == str(novo):
            return
        base.at[i, campo] = novo
        trocas.append({"doc_uid": d["doc_uid"], "campo": campo,
                       "antes": None if _vazio(antes) else str(antes), "depois": str(novo),
                       "motivo": motivo, "id_lastro": d.get("id_lastro"), "confirmacao": "revisar"})

    for d in decisoes:
        uid = d.get("doc_uid")
        fonte = d.get("fonte_decisao") or ""
        if fonte == "humano_pendente":
            if uid not in humano:
                contar("humano_sem_resposta")
                continue
            d = {**d, **humano[uid]}
            fonte = "humano"
        if _vazio(uid) or uid not in pos:
            contar("sem_documento_no_banco")
            continue
        if uid in ja_feitos:
            contar("ja_aplicado")
            continue
        i = pos[uid]
        motivo = f"revisar:{fonte}"
        mudou = False
        if d.get("escolha_resumo") in TROCAM and not _vazio(d.get("resumo")):
            novo = espacos(d["resumo"])
            if texto_comparavel(novo) != texto_comparavel(base.at[i, "description"]):
                trocar(i, "description", novo, motivo, d)
                mudou = True
                tip, esp = base.at[i, "extracted_typology"], especie(novo)
                if esp and (_vazio(tip) or not novo.startswith(str(tip).strip().lstrip("["))):
                    trocar(i, "extracted_typology", esp, motivo, d)
        if d.get("escolha_data") in TROCAM:
            data = nova_data(base.at[i, "document_id_and_date"], d.get("data"))
            if data:
                trocar(i, "document_id_and_date", data, motivo, d)
                mudou = True
                ano = _ANO.search(str(d.get("data")))
                if ano and _vazio(base.at[i, "ano_isolado"]):
                    trocar(i, "ano_isolado", int(ano.group(1)), motivo, d)
        contar(f"{fonte}:{'mudou' if mudou else 'fica'}")

    base["ano_isolado"] = base["ano_isolado"].astype("Int64")
    return base, pd.DataFrame(trocas, columns=COLUNAS_LOG), contagem


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--decisoes", required=True, type=Path)
    ap.add_argument("--humano", type=Path)
    ap.add_argument("--colecao", default="ahu-brasil")
    ap.add_argument("--corpus", default=RAIZ / "corpus", type=Path)
    a = ap.parse_args(argv)

    pasta = a.corpus / "colecoes" / a.colecao
    base = pd.read_parquet(pasta / "documentos.parquet")
    arq_log = pasta / "correcoes_lastro.parquet"
    log = pd.read_parquet(arq_log) if arq_log.exists() else pd.DataFrame(columns=COLUNAS_LOG)
    feitos = set(log.loc[log["motivo"].astype(str).str.startswith("revisar:"), "doc_uid"])
    humano = ler_humano(a.humano) if a.humano else None

    nova, trocas, contagem = aplicar(base, ler_decisoes(a.decisoes), humano, feitos)
    nova.to_parquet(pasta / "documentos.parquet", index=False)
    pd.concat([log, trocas], ignore_index=True).to_parquet(arq_log, index=False)

    camada = json.loads((pasta / "camada.json").read_text("utf-8"))
    registro = camada.setdefault("revisao_lastro", {"aplicacoes": []})
    registro["aplicacoes"].append({
        "script": "build/aplicar_revisao_lastro.py",
        "decisoes": a.decisoes.name,
        "humano": a.humano.name if a.humano else None,
        "documentos_alterados": int(trocas["doc_uid"].nunique()),
        "por_campo": {k: int(v) for k, v in trocas["campo"].value_counts().items()},
        "contagem": contagem,
    })
    (pasta / "camada.json").write_text(json.dumps(camada, ensure_ascii=False, indent=2) + "\n", "utf-8")
    atualizar_manifesto(a.corpus, a.colecao, pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds"))
    print(json.dumps(registro["aplicacoes"][-1], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
