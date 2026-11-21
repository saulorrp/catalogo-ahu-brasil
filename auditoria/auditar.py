"""Auditoria do banco contra o lastro (PDFs do ACTD) e contra o MAPE, e montagem do padrão ouro.

Uso:
    python auditoria/auditar.py --ouro ouro_actd.jsonl --mape mape_dataset_version_6.csv --saida PASTA

    --ouro   saída de auditoria/extrair_actd.py (extração independente do lastro)
    --mape   CSV do dataset MAPE (doi:10.5281/zenodo.24403753)
    --banco  coleção do catálogo (padrão: corpus/colecoes/ahu-brasil/documentos.parquet)

Para cada verbete do lastro, compara o resumo e a data com o banco e com o MAPE e classifica a
diferença. O padrão ouro é o texto do lastro, com o grau de confirmação: "tripla" quando banco e
MAPE dão o mesmo texto, "dupla" quando um dos dois dá, "lastro" quando nenhum dá mas a diferença
do banco é um erro de leitura conhecido (resumo cortado, data no resumo, número de inventário
colado), "revisar" nos demais casos ou quando a própria extração levantou dúvida. Grava:
    padrao_ouro.parquet       um registro por verbete do lastro (séries do Brasil)
    banco_x_lastro.csv        documentos do banco cujo resumo ou data diferem do lastro
    mape_x_lastro.csv         pares do MAPE cujo resumo difere do lastro
    sem_par.csv               documentos do banco sem verbete no lastro, e verbetes sem documento
    resumo.json               as contagens
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from auditoria.extrair_actd import dobrar  # noqa: E402
from build.importar_mape import chave_referencia, ler_mape, semelhanca, texto_comparavel  # noqa: E402

# PDFs do ACTD que não são do Brasil: ficam no lastro, mas fora da auditoria
FORA = {
    "CU-Angola-Parcial.pdf",
    "CU-CaboVerde-Parcial.pdf",
    "CU-Guine-Parcial.pdf",
    "CU-India.pdf",
    "CU-Macau.pdf",
    "CU-Mocambique-Parcial.pdf",
    "CU-SaoTome-Parcial.pdf",
    "CU-Timor.pdf",
}
ERROS_DO_BANCO = {
    "sobra_no_fim",
    "sem_inicio_que_foi_para_a_data",
    "data_no_resumo",
    "sem_fim",
    "sem_inicio",
    "resumo_na_data",
    "vazio",
}
MARCAS_DUVIDA = {"data_com_colchete_aberto", "resumo_sem_especie", "sem_resumo"}


def chave_texto(cota: str | None) -> str | None:
    """Chave da cota do Resgate tolerante a erros de digitação ("AHU CU_016", "Cx, 1", "Cx. 164 -A",
    "Cx. 6, 720.", "pasta"): série|caixa|documento ou pasta (primeiro número)."""
    if not cota:
        return None
    t = re.sub(r"\s+", "", dobrar(cota).upper())
    m = re.search(
        r"CU_?(\d{3}(?:-\d+)?|REINO)[,;.]*C\.?X[.,]*(\d+)-?([A-Z]?)[,.;]*(?:D\.?|DOC\.?|PASTA)?(\d+)", t
    )
    if not m:
        return None
    serie = m.group(1)
    if serie[0].isdigit():
        p = serie.split("-")
        serie = str(int(p[0])) + (f"-{int(p[1])}" if len(p) > 1 else "")
    return f"{serie}|{int(m.group(2))}{m.group(3)}|{int(m.group(4))}"


def chave(ref, cota) -> str | None:
    return chave_texto(cota) or chave_referencia(ref, cota)


def sem_numero(data: str | None) -> str:
    return re.sub(r"^\s*\d{1,5}[A-Z]?(?:\s*[-–]\s*\d{1,5})?\s*[-–.]?(?:\s+|$)", "", data or "").strip()


def classificar(banco: str, ouro: str, data_banco: str = "") -> str:
    a, b = texto_comparavel(banco), texto_comparavel(ouro)
    if a == b:
        return "igual"
    if not b:
        return "fonte_sem_resumo"
    if not a:
        d = texto_comparavel(data_banco)
        return "resumo_na_data" if d and b[:30] in d else "vazio"
    if b.endswith(a):
        d = texto_comparavel(data_banco)
        return (
            "sem_inicio_que_foi_para_a_data"
            if d and d.endswith(b[: len(b) - len(a)].strip())
            else "sem_inicio"
        )
    if b.startswith(a):
        return "sem_fim"
    if a.startswith(b):
        return "sobra_no_fim"
    if a.endswith(b):
        return "sobra_no_inicio"
    if b and a.endswith(b[-60:]) and len(a) > len(b):
        return "sobra_no_inicio"
    if b in a:
        return "sobra_nas_pontas"
    if a in b:
        return "trecho"
    s = semelhanca(a, b)
    return "variante" if s >= 0.95 else "parecido" if s >= 0.8 else "diferente"


def sobra(banco: str, ouro: str) -> str:
    """O que o banco tem a mais no fim (por exemplo 'Nº de inventário no catálogo: 3')."""
    a, b = texto_comparavel(banco), texto_comparavel(ouro)
    if a.startswith(b):
        resto = a[len(b) :].strip()
        if "de inventario" in resto[:20]:
            return "inventario"
        if resto.startswith(("anexo", "em anexo")):
            return "anexo"
        if resto.startswith("obs"):
            return "obs"
        if resto.startswith("ahu"):
            return "cota"
        return "outro"
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ouro", required=True)
    ap.add_argument("--mape", required=True)
    ap.add_argument("--banco", default=str(RAIZ / "corpus/colecoes/ahu-brasil/documentos.parquet"))
    ap.add_argument("--saida", required=True)
    ap.add_argument("--govbr", help="saída de auditoria/verificar_govbr.py, para juntar ao padrão ouro")
    a = ap.parse_args()
    out = Path(a.saida)
    out.mkdir(parents=True, exist_ok=True)

    ouro = pd.read_json(a.ouro, lines=True)
    ouro = ouro[~ouro.arquivo.isin(FORA)].reset_index(drop=True)
    ouro["chave"] = [chave(r, c) for r, c in zip(ouro.reference_code, ouro.cota_texto)]
    ouro["chave_ref"] = [chave_referencia(r, c) for r, c in zip(ouro.reference_code, ouro.cota_texto)]
    ouro["id_lastro"] = ouro.arquivo.str.replace(".pdf", "", regex=False) + "#" + ouro.ordem.astype(str)

    banco = pd.read_parquet(a.banco)
    banco["arquivo"] = banco.url_actd.str.extract(r"/([^/]+\.pdf)$")[0]
    banco["chave"] = [chave(r, c) for r, c in zip(banco.reference_code, banco.new_code)]
    banco["data_sem_numero"] = banco.document_id_and_date.map(sem_numero)

    mape = ler_mape(Path(a.mape))
    mape = mape.dropna(subset=["chave"]).drop_duplicates("chave").set_index("chave")

    # banco -> lastro: mesma chave; se o banco diz de que PDF veio, no mesmo PDF
    idx = {}
    for i, (arq, ch) in enumerate(zip(ouro.arquivo, ouro.chave)):
        if ch:
            idx.setdefault(ch, []).append(i)
    # pareamento um a um: a mesma cota pode aparecer mais de uma vez (o catálogo de Minas repete
    # blocos inteiros); com o mesmo número de ocorrências dos dois lados, pareia pela ordem
    por_chave = {}
    for j, (arq, ch) in enumerate(zip(banco.arquivo, banco.chave)):
        por_chave.setdefault(ch, []).append(j)
    pares, sem_lastro = [], []
    for ch, js in por_chave.items():
        cand = idx.get(ch, []) if ch else []
        arqs = {banco.arquivo[j] for j in js if isinstance(banco.arquivo[j], str)}
        if arqs:
            cand = [i for i in cand if ouro.arquivo[i] in arqs] or cand
        if not cand:
            sem_lastro += js
            continue
        if len(cand) == len(js):
            pares += list(zip(js, cand))
            continue
        livres = list(cand)
        for j in js:
            if not livres:
                sem_lastro.append(j)
                continue
            desc = texto_comparavel(banco.description[j])
            i = max(livres, key=lambda i: semelhanca(desc, texto_comparavel(ouro.resumo[i])))
            pares.append((j, i))
            if len(livres) > 1 or len(js) <= len(cand):
                livres.remove(i)
    # segunda passada, só com as sobras de cada PDF: cota com erro de digitação de um dos lados
    # ("Cx. , D. 1138", ".AHU_CU_008"); pareia pelo número do documento e pelo texto
    usados_o = {i for _, i in pares}
    sobra_o = {}
    for i in range(len(ouro)):
        if i not in usados_o:
            sobra_o.setdefault(ouro.arquivo[i], []).append(i)
    ainda = []
    for j in sem_lastro:
        arq = banco.arquivo[j]
        livres = sobra_o.get(arq, []) if isinstance(arq, str) else []
        nd = re.findall(r"\d+", str(banco.new_code[j]))
        desc = texto_comparavel(banco.description[j])
        melhor, nota = None, 0.0
        for i in livres:
            no = re.findall(r"\d+", str(ouro.cota_texto[i]))
            mesmo_doc = bool(nd and no and nd[-1] == no[-1])
            sm = semelhanca(desc, texto_comparavel(ouro.resumo[i])) if (mesmo_doc or len(livres) < 400) else 0
            if (mesmo_doc and sm >= 0.6 or sm >= 0.9) and sm > nota:
                melhor, nota = i, sm
        if melhor is None:
            ainda.append(j)
        else:
            pares.append((j, melhor))
            livres.remove(melhor)
    sem_lastro = ainda
    pb = pd.DataFrame(pares, columns=["j", "i"])
    usados = Counter(pb.i)

    linhas = []
    for j, i in pares:
        b, o = banco.iloc[j], ouro.iloc[i]
        cls = classificar(b.description or "", o.resumo or "", b.document_id_and_date or "")
        if cls == "sobra_no_inicio":
            extra = texto_comparavel(b.description)[
                : len(texto_comparavel(b.description)) - len(texto_comparavel(o.resumo))
            ].strip()
            dl = texto_comparavel(o.data)
            if extra and (
                extra in dl
                or dl.endswith(extra)
                or re.fullmatch(r"(v|s) d( \d+)?", extra)
                or (len(extra) < 80 and re.search(r"\b1[4-9]\d\d\b", extra))
            ):
                cls = "data_no_resumo"
        cls_data = (
            "igual"
            if texto_comparavel(b.data_sem_numero) == texto_comparavel(o.data)
            else "data_com_texto_do_resumo"
            if texto_comparavel(b.data_sem_numero).startswith(texto_comparavel(o.data)) and o.data
            else "diferente"
        )
        linhas.append(
            {
                "doc_uid": b.doc_uid,
                "id_lastro": o.id_lastro,
                "folder": b.folder,
                "new_code": b.new_code,
                "reference_code": b.reference_code,
                "arquivo": o.arquivo,
                "pagina_pdf": o.pagina_inicio,
                "pagina_banco": b.pagina_actd,
                "classe_resumo": cls,
                "sobra": sobra(b.description or "", o.resumo or "") if cls == "sobra_no_fim" else "",
                "classe_data": cls_data,
                "data_banco": b.data_sem_numero,
                "data_lastro": o.data,
                "resumo_banco": b.description,
                "resumo_lastro": o.resumo,
            }
        )
    bx = pd.DataFrame(linhas)

    # MAPE -> lastro
    ml = []
    for o in ouro.itertuples(index=False):
        if o.chave_ref in mape.index:
            m = mape.loc[o.chave_ref]
            ml.append(
                {
                    "id_lastro": o.id_lastro,
                    "mape_doc_id": int(m.doc_id),
                    "mape_reference_code": m.reference_code,
                    "classe_resumo": classificar(
                        m.Doc_Text_Port if "Doc_Text_Port" in m else m.doc_text_portuguese, o.resumo or ""
                    ),
                    "resumo_mape": m.Doc_Text_Port if "Doc_Text_Port" in m else m.doc_text_portuguese,
                    "resumo_lastro": o.resumo,
                    "arquivo": o.arquivo,
                }
            )
    mx = pd.DataFrame(ml)

    # padrão ouro
    g = ouro[
        [
            "id_lastro",
            "arquivo",
            "ordem",
            "numero",
            "data",
            "resumo",
            "anexo",
            "obs",
            "nota",
            "inventario",
            "remissao",
            "cota_antiga",
            "cota_texto",
            "reference_code",
            "chave",
            "pagina_inicio",
            "pagina_fim",
            "marcas",
        ]
    ].copy()
    g = g.merge(
        bx[["id_lastro", "doc_uid", "classe_resumo", "classe_data"]].rename(
            columns={"classe_resumo": "banco_resumo", "classe_data": "banco_data"}
        ),
        on="id_lastro",
        how="left",
    )
    g = g.merge(
        mx[["id_lastro", "mape_doc_id", "classe_resumo"]].rename(columns={"classe_resumo": "mape_resumo"}),
        on="id_lastro",
        how="left",
    )
    duvida = g.marcas.map(lambda ms: bool(set(ms) & MARCAS_DUVIDA))
    ok_b, ok_m = g.banco_resumo.eq("igual"), g.mape_resumo.eq("igual")
    g["confirmacao"] = "revisar"
    g.loc[(ok_b | ok_m) & ~duvida, "confirmacao"] = "dupla"
    g.loc[ok_b & ok_m & ~duvida, "confirmacao"] = "tripla"
    # o lastro sozinho, quando a diferença do banco é um erro de leitura conhecido e a extração
    # do lastro não levantou dúvida
    explicado = g.banco_resumo.isin(ERROS_DO_BANCO) & ~duvida & (g.confirmacao == "revisar")
    g.loc[explicado, "confirmacao"] = "lastro"
    g.loc[g.chave.duplicated(keep=False) & g.chave.notna(), "marcas"] = g.marcas.map(
        lambda m: list(m) + ["cota_repetida_no_lastro"]
    )
    g["marcas"] = g.marcas.map(lambda m: ";".join(m))
    g["fonte"] = "actd"
    if a.govbr:
        gv = pd.read_csv(a.govbr).merge(
            banco[["doc_uid", "document_id_and_date", "caminho_resgate"]],
            on="doc_uid",
            how="left",
            suffixes=("", "_b"),
        )
        gg = pd.DataFrame(
            {
                "id_lastro": "govbr#" + gv.doc_uid,
                "arquivo": gv.caminho_resgate,
                "data": gv.document_id_and_date.map(sem_numero),
                "resumo": gv.resumo_banco,
                "cota_texto": gv.new_code,
                "doc_uid": gv.doc_uid,
                "fonte": "govbr",
                "banco_resumo": gv.classe.map({"resumo_encontrado": "igual"}).fillna(gv.classe),
                "marcas": gv.cota_suja.map({True: "cota_suja", False: ""}),
            }
        )
        gg["confirmacao"] = gg.banco_resumo.map(lambda c: "dupla" if c == "igual" else "revisar")
        g = pd.concat([g, gg], ignore_index=True)
    # cota com texto de outro campo grudado (o resumo ou o título do catálogo entrou na cota)
    sujas = banco[banco.new_code.fillna("").str.len() > 70]
    sujas[["doc_uid", "folder", "new_code"]].to_csv(out / "cotas_sujas.csv", index=False)
    g.to_parquet(out / "padrao_ouro.parquet", index=False)

    bx[(bx.classe_resumo != "igual") | (bx.classe_data != "igual")].to_csv(
        out / "banco_x_lastro.csv", index=False
    )
    mx[mx.classe_resumo != "igual"].to_csv(out / "mape_x_lastro.csv", index=False)
    sp = banco.iloc[sem_lastro][
        ["doc_uid", "folder", "new_code", "reference_code", "arquivo", "fonte_texto"]
    ].assign(lado="so_no_banco")
    so = g[g.doc_uid.isna()][["id_lastro", "arquivo", "cota_texto", "reference_code", "resumo"]].assign(
        lado="so_no_lastro"
    )
    pd.concat([sp, so]).to_csv(out / "sem_par.csv", index=False)

    resumo = {
        "verbetes_no_lastro": int(len(g)),
        "documentos_no_banco": int(len(banco)),
        "banco_com_par_no_lastro": int(len(bx)),
        "banco_sem_par": int(len(sem_lastro)),
        "banco_sem_par_com_url_actd": int(banco.iloc[sem_lastro].url_actd.notna().sum()),
        "lastro_sem_par_no_banco": int(len(so)),
        "verbete_do_lastro_usado_por_mais_de_um_documento": int(sum(1 for n in usados.values() if n > 1)),
        "banco_x_lastro_resumo": bx.classe_resumo.value_counts().to_dict(),
        "banco_x_lastro_sobra": bx[bx.sobra != ""].sobra.value_counts().to_dict(),
        "banco_x_lastro_data": bx.classe_data.value_counts().to_dict(),
        "mape_x_lastro_resumo": mx.classe_resumo.value_counts().to_dict() if len(mx) else {},
        "padrao_ouro_confirmacao": g.confirmacao.value_counts().to_dict(),
        "padrao_ouro_por_fonte": g.groupby(["fonte", "confirmacao"])
        .size()
        .unstack(fill_value=0)
        .to_dict("index"),
        "cotas_sujas_no_banco": int(len(sujas)),
        "marcas_da_extracao": Counter(m for ms in ouro.marcas for m in ms),
        "por_serie_banco_diferente": bx[bx.classe_resumo != "igual"]
        .groupby("folder")
        .size()
        .sort_values(ascending=False)
        .to_dict(),
    }
    (out / "resumo.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=1, default=int), "utf-8")
    print(json.dumps(resumo, ensure_ascii=False, indent=1, default=int))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
