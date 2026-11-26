"""corrigir_sergipe.py — Aplica as cotas oficiais AHU/DigitArq em Sergipe (série 022).

O que faz sobre o corpus (idempotente):
1. Nos 491 verbetes de Sergipe vindos da página do gov.br (Grupo A):
   - Preserva a numeração da edição impressa (9 caixas) em `old_code`.
   - Substitui `new_code` e `reference_code` pela cota oficial AHU/DigitArq (6 caixas, D. 1–495).
   - Remove o rodapé editorial colado na descrição do verbete 495 (`Elaboração e revisão...`).
2. Recupera os 3 verbetes ausentes da coleção (107, 193, 382; o 119 já existe em `ahu-brasil:b5d3136fdf`)
   diretamente do HTML do gov.br, atribuindo `doc_uid` determinístico e atualizando `tipologia_v1`.
3. Acrescenta as 46 duplicatas reais do Grupo B em `corpus/duplicatas.ignore` apontando para o
   `doc_uid` correspondente do Grupo A (sem apagar nenhum `doc_uid`).
4. Lista os 14 registros do Grupo B cuja cota impressa leva a outro documento (4 falsos Sergipe da
   série `003` e 10 com `Cx. 2` trocada). Eles não são bloqueados aqui: a cota certa e a prova de
   cada um estão em `corpus/cotas_corrigidas.tsv` (revisão de 24/11/2026, depois da 1.ª versão
   deste script, que os gravava em `corpus/cotas_reconstruidas.ignore` como "erro tipográfico").
5. Atualiza `camada.json`, `registro_ids.json` e `corpus/manifest.json` com os novos SHA-256.

Rodou uma vez, em 24/11/2026, no Hermerico. Precisa do HTML da página de Sergipe do gov.br em
`arquivos-do-projeto/` (fora do Git): no GitHub fica como registro do que foi feito.

Uso: python coleta/scripts/corrigir_sergipe.py [--html CAMINHO_HTML_SERGIPE]
"""
from __future__ import annotations

import argparse
import hashlib
import html as html_lib
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from build.importar_base import commit_atual, sha256_arquivo  # noqa: E402
from coleta.scripts.parse_sergipe import RODAPE_PAGINA, caixa_oficial_022  # noqa: E402

CORPUS = RAIZ / "corpus"
COLECAO_DIR = CORPUS / "colecoes" / "ahu-brasil"
COLECAO_PQ = COLECAO_DIR / "documentos.parquet"
TIPOLOGIA_DIR = CORPUS / "camadas" / "tipologia_v1"
TIPOLOGIA_PQ = TIPOLOGIA_DIR / "tipologia.parquet"
MANIFESTO = CORPUS / "manifest.json"
DUPLICATAS_IGN = CORPUS / "duplicatas.ignore"

URL_SERGIPE_GOVBR = (
    "https://www.gov.br/bn/pt-br/central-de-conteudos/projeto-resgate/"
    "novos-instrumentos-de-pesquisa/catalogo-de-documentos-manuscritos-avulsos-"
    "da-capitania-de-sergipe-1619-1822/avulsos-sergipe-1619-1822"
)
HTML_PADRAO = (
    RAIZ
    / "arquivos-do-projeto"
    / "resgate"
    / "raw"
    / "catalogo-de-documentos-manuscritos-avulsos-da-capitania-de-sergipe-1619-1822__avulsos-sergipe-1619-1822.html"
)

# 4 registros da série 003 com cota 022. Dois são erro tipográfico do ACTD (CU-BrasilGeral.pdf,
# p. 39 e 40); nos outros dois o nosso parser do catálogo temático leu a cota da observação
# ("Obs.: ver consulta em AHU_ACL_CU_022, ..."), e são cópias de 757cff7014 e 922f336405.
# A correção de todos está em corpus/cotas_corrigidas.tsv.
FALSOS_SERGIPE_003 = {
    "ahu-brasil:eabc8842f1": "PT/AHU/CU/003/0002/00173 (erro tipográfico 022 em CU-BrasilGeral.pdf, p. 39)",
    "ahu-brasil:82674729c0": "PT/AHU/CU/003/0002/00176 (erro tipográfico 022 em CU-BrasilGeral.pdf, p. 40)",
    "ahu-brasil:739d214bb9": "PT/AHU/CU/003/0004/00419 (cota lida da observação; repete 757cff7014)",
    "ahu-brasil:73ce1692b0": "PT/AHU/CU/003/0032/02637 (cota lida da observação; repete 922f336405)",
}

RE_OLD_FROM_NEW = re.compile(r"Cx\.\s*(\d+),\s*D\.\s*(\d+)\s*([A-Z])?", re.I)
RE_VERBETE = re.compile(r"^\s*(\d+)\b")
RE_ANO = re.compile(r"\b(1[5-8]\d\d)\b")
RE_CAB_HTML = re.compile(
    r"Caixa\s*:?\s*(\d+)\s*(?:,\s*Documento\s*N[º°o]?|Identifica[çc][ãa]o)\s*:?\s*(\d+)\s*(?:-\s*([A-Z]))?\s*,?\s*(.*)",
    re.I,
)


def _chave_tipologia(tip: str) -> str:
    t = unicodedata.normalize("NFKD", tip)
    t = "".join(c for c in t if not unicodedata.combining(c)).upper()
    return re.sub(r"\s+", " ", t).strip()


def _limpar_html(fragmento: str) -> str:
    txt = re.sub(r"<[^>]+>", " ", fragmento)
    txt = html_lib.unescape(txt)
    return re.sub(r"\s+", " ", txt).strip()


def extrair_verbetes_faltantes_html(html_path: Path, numeros: tuple[int, ...] = (107, 193, 382)) -> list[dict]:
    """Extrai diretamente do HTML do gov.br os verbetes perdidos pelo parser antigo."""
    raw = html_path.read_text(encoding="utf-8", errors="replace")
    trs = re.findall(r"<tr\b[^>]*>(.*?)</tr>", raw, re.I | re.S)
    achados = []
    for i, tr in enumerate(trs):
        m_num = re.search(r">(\d+)</a>", tr)
        if not m_num:
            continue
        num = int(m_num.group(1))
        if num not in numeros:
            continue
        tds = re.findall(r"<td\b[^>]*>(.*?)</td>", tr, re.I | re.S)
        if len(tds) < 2:
            continue
        cab = _limpar_html(tds[1])
        mc = RE_CAB_HTML.match(cab)
        if not mc:
            continue
        desc = ""
        if i + 1 < len(trs):
            tds_next = re.findall(r"<td\b[^>]*>(.*?)</td>", trs[i + 1], re.I | re.S)
            if len(tds_next) >= 2:
                desc = RODAPE_PAGINA.sub("", _limpar_html(tds_next[1])).strip()
        cx_imp, doc_imp, suf_imp = int(mc.group(1)), int(mc.group(2)), mc.group(3) or ""
        data_local = mc.group(4).strip()
        cx_of = caixa_oficial_022(num)
        assert cx_of is not None
        ref = f"PT/AHU/CU/022/{cx_of:04d}/{num:05d}"
        new_code = f"AHU_ACL_CU_022, Cx. {cx_of}, D. {num}."
        old_code = f"AHU-Sergipe, cx. {cx_imp:02d}, doc. {doc_imp:02d}{suf_imp}."
        did = f"{num}. {data_local}" if data_local else f"{num}."
        m_ano = RE_ANO.search(data_local)
        ano = int(m_ano.group(1)) if m_ano else pd.NA
        # Tipologia literal da primeira expressão (Carta Patente / Consulta / Carta)
        if desc.upper().startswith("CARTA PATENTE"):
            tip = "CARTA PATENTE"
        else:
            tip = desc.split()[0].strip(",.").upper() if desc else None
        uid_hash = hashlib.sha1(f"ahu-brasil|{URL_SERGIPE_GOVBR}|{ref}".encode()).hexdigest()[:10]
        achados.append(
            {
                "doc_uid": f"ahu-brasil:{uid_hash}",
                "colecao": "ahu-brasil",
                "folder": "Sergipe d’el-Rei",
                "description": desc,
                "old_code": old_code,
                "new_code": new_code,
                "reference_code": ref,
                "document_id_and_date": did,
                "ano_isolado": ano,
                "extracted_typology": tip,
                "caminho_resgate": URL_SERGIPE_GOVBR,
                "url_actd": None,
                "pagina_actd": float("nan"),
                "fonte_texto": (
                    f"Biblioteca Nacional, Projeto Resgate, Avulsos - Sergipe (1619-1822) (gov.br), "
                    f"{URL_SERGIPE_GOVBR} (acesso em 22/10/2026)"
                ),
                "qc": None,
            }
        )
    if len(achados) != len(numeros):
        falt = set(numeros) - {int(RE_VERBETE.match(a["document_id_and_date"]).group(1)) for a in achados}
        raise RuntimeError(f"Não foram encontrados no HTML os verbetes: {sorted(falt)}")
    return achados


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--html", type=Path, default=HTML_PADRAO)
    args = ap.parse_args()

    docs = pd.read_parquet(COLECAO_PQ)
    tip_df = pd.read_parquet(TIPOLOGIA_PQ)

    # 1. Grupo A: linhas vindas da página de Sergipe do gov.br
    mask_ga = docs["caminho_resgate"] == URL_SERGIPE_GOVBR
    uid_por_verbete_ga: dict[int, str] = {}
    corrigidos_ga = 0
    rodape_495_cortado = False

    for idx in docs.index[mask_ga]:
        did = str(docs.at[idx, "document_id_and_date"] or "")
        mv = RE_VERBETE.match(did)
        if not mv:
            continue
        verb = int(mv.group(1))
        cx_of = caixa_oficial_022(verb)
        if cx_of is None:
            continue

        # Preservar cota da edição impressa (9 caixas) em old_code se ainda não estiver gravada
        if pd.isna(docs.at[idx, "old_code"]) or not str(docs.at[idx, "old_code"]).strip():
            m_imp = RE_OLD_FROM_NEW.search(str(docs.at[idx, "new_code"] or ""))
            if m_imp:
                cx_i, d_i, s_i = int(m_imp.group(1)), int(m_imp.group(2)), m_imp.group(3) or ""
                docs.at[idx, "old_code"] = f"AHU-Sergipe, cx. {cx_i:02d}, doc. {d_i:02d}{s_i}."

        nova_cota = f"AHU_ACL_CU_022, Cx. {cx_of}, D. {verb}."
        nova_ref = f"PT/AHU/CU/022/{cx_of:04d}/{verb:05d}"
        if docs.at[idx, "new_code"] != nova_cota or docs.at[idx, "reference_code"] != nova_ref:
            docs.at[idx, "new_code"] = nova_cota
            docs.at[idx, "reference_code"] = nova_ref
            corrigidos_ga += 1
        if docs.at[idx, "qc"] == "cota_repetida":
            docs.at[idx, "qc"] = None

        if verb == 495:
            desc = str(docs.at[idx, "description"] or "")
            limpa = RODAPE_PAGINA.sub("", desc).strip()
            if limpa != desc:
                docs.at[idx, "description"] = limpa
                rodape_495_cortado = True

        uid_por_verbete_ga[verb] = str(docs.at[idx, "doc_uid"])

    # 2. Recuperar os 3 verbetes faltantes (107, 193, 382) do HTML do gov.br
    novos_docs = []
    novas_tips = []
    faltantes = extrair_verbetes_faltantes_html(args.html, (107, 193, 382))
    uids_existentes = set(docs["doc_uid"])
    for item in faltantes:
        verb = int(RE_VERBETE.match(item["document_id_and_date"]).group(1))
        if item["doc_uid"] not in uids_existentes and verb not in uid_por_verbete_ga:
            novos_docs.append(item)
            tip_val = item["extracted_typology"]
            novas_tips.append(
                {
                    "doc_uid": item["doc_uid"],
                    "tipologia_bruta": tip_val,
                    "tipologia": tip_val,
                    "tipologia_chave": _chave_tipologia(tip_val) if tip_val else None,
                    "typology_status": bool(tip_val),
                    "tipologia_corrigida": False,
                }
            )
            uid_por_verbete_ga[verb] = item["doc_uid"]

    if novos_docs:
        docs = pd.concat([docs, pd.DataFrame(novos_docs)], ignore_index=True)
        docs["ano_isolado"] = docs["ano_isolado"].astype("Int64")
        tip_df = pd.concat([tip_df, pd.DataFrame(novas_tips)], ignore_index=True)
        tip_df["typology_status"] = tip_df["typology_status"].astype(bool)
        tip_df["tipologia_corrigida"] = tip_df["tipologia_corrigida"].astype(bool)

    # 3. Analisar Grupo B (outras linhas em série 022 fora do gov.br)
    mask_gb = (
        docs["reference_code"].astype(str).str.startswith("PT/AHU/CU/022/")
        & (docs["caminho_resgate"] != URL_SERGIPE_GOVBR)
    )
    dups_sergipe: list[tuple[str, str, str]] = []  # (uid_dup, uid_mantido, cota_oficial)
    cxs_erradas_gb: list[tuple[str, str]] = []  # (uid, nota)
    for _, r in docs[mask_gb].iterrows():
        uid = str(r["doc_uid"])
        ref = str(r["reference_code"])
        if uid in FALSOS_SERGIPE_003:
            continue
        m_ref = re.match(r"PT/AHU/CU/022/(\d+)/(\d+)", ref)
        if not m_ref:
            continue
        cx_atual, doc_num = int(m_ref.group(1)), int(m_ref.group(2))
        cx_of = caixa_oficial_022(doc_num)
        if cx_of is not None and cx_atual != cx_of:
            cxs_erradas_gb.append(
                (uid, f"{r['new_code']} (caixa diverge do AHU/DigitArq: Cx. {cx_of}, D. {doc_num})")
            )
        if doc_num in uid_por_verbete_ga and uid_por_verbete_ga[doc_num] != uid:
            cota_of = f"AHU_ACL_CU_022, Cx. {cx_of}, D. {doc_num}."
            dups_sergipe.append((uid, uid_por_verbete_ga[doc_num], cota_of))

    # 4. Gravar coleção e tipologia atualizadas
    docs.to_parquet(COLECAO_PQ, index=False)
    tip_df.to_parquet(TIPOLOGIA_PQ, index=False)

    # Atualizar metadados (camada.json, registro_ids.json e manifest.json)
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for arq_json, n_docs in [(COLECAO_DIR / "camada.json", len(docs)), (COLECAO_DIR / "registro_ids.json", len(docs))]:
        obj = json.loads(arq_json.read_text(encoding="utf-8"))
        obj["documentos"] = int(n_docs)
        if "data" in obj:
            obj["data"] = agora
        arq_json.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    tip_camada = json.loads((TIPOLOGIA_DIR / "camada.json").read_text(encoding="utf-8"))
    tip_camada["documentos"] = int(len(tip_df))
    tip_camada["data"] = agora
    (TIPOLOGIA_DIR / "camada.json").write_text(json.dumps(tip_camada, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    man = json.loads(MANIFESTO.read_text(encoding="utf-8"))
    man["colecoes"]["ahu-brasil"]["atualizado_em"] = agora
    man["colecoes"]["ahu-brasil"]["arquivos"]["colecoes/ahu-brasil/documentos.parquet"] = sha256_arquivo(COLECAO_PQ)
    man["colecoes"]["ahu-brasil"]["arquivos"]["colecoes/ahu-brasil/registro_ids.json"] = sha256_arquivo(COLECAO_DIR / "registro_ids.json")
    man["colecoes"]["ahu-brasil"]["arquivos"]["colecoes/ahu-brasil/camada.json"] = sha256_arquivo(COLECAO_DIR / "camada.json")
    man["camadas"]["tipologia_v1"]["documentos"] = int(len(tip_df))
    man["camadas"]["tipologia_v1"]["arquivos"]["camadas/tipologia_v1/tipologia.parquet"] = sha256_arquivo(TIPOLOGIA_PQ)
    man["camadas"]["tipologia_v1"]["arquivos"]["camadas/tipologia_v1/camada.json"] = sha256_arquivo(TIPOLOGIA_DIR / "camada.json")
    MANIFESTO.write_text(json.dumps(man, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 5. Atualizar corpus/duplicatas.ignore (sem duplicar linhas já presentes)
    linhas_dup = DUPLICATAS_IGN.read_text(encoding="utf-8").splitlines()
    uids_ja_dup = {
        l.split("#", 1)[0].strip() for l in linhas_dup if l.strip() and not l.lstrip().startswith("#")
    }
    adicionadas_dup = 0
    for uid_dup, uid_ok, cota_of in sorted(dups_sergipe):
        if uid_dup not in uids_ja_dup:
            linhas_dup.append(f"{uid_dup}  # repete {uid_ok} | {cota_of}")
            uids_ja_dup.add(uid_dup)
            adicionadas_dup += 1
    DUPLICATAS_IGN.write_text("\n".join(linhas_dup) + "\n", encoding="utf-8")

    # 6. As 14 cotas do Grupo B que levam a outro documento: só listadas (ver corpus/cotas_corrigidas.tsv)
    for uid, nota in sorted(FALSOS_SERGIPE_003.items()) + sorted(cxs_erradas_gb):
        print(f"cota a corrigir em corpus/cotas_corrigidas.tsv: {uid}  # {nota}", file=sys.stderr)

    print(
        json.dumps(
            {
                "corrigidos_grupo_a": corrigidos_ga,
                "rodape_495_cortado": rodape_495_cortado,
                "verbetes_recuperados": [d["reference_code"] for d in novos_docs],
                "total_colecao": len(docs),
                "total_tipologia": len(tip_df),
                "duplicatas_sergipe_adicionadas": adicionadas_dup,
                "cotas_a_corrigir": len(FALSOS_SERGIPE_003) + len(cxs_erradas_gb),
                "commit_base": commit_atual(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
