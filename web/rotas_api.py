import re
from bisect import bisect_right

import pandas as pd
from fastapi import APIRouter, HTTPException, Request

import web.main as main_module
from ahu.busca import chave_cota, tabela_de_cotas
from ahu.ficha import montar
from web import cache
from web.core import parse_consulta

router = APIRouter()

_RE_COTA_CURTA = re.compile(
    r"^\s*(\d{3})(?:[.-](\d{1,3}))?[-_ ](\d{1,4})[-_ ](\d{1,5})(?![\d.])"
)


def _normalizar_cota_entrada(texto: str) -> str:
    """Aceita também a cota curta (`021-0006-00390`, `017.001-0057-13257`)."""
    m = _RE_COTA_CURTA.match(texto or "")
    if not m:
        return texto
    serie = m.group(1) + (f"-{int(m.group(2)):03d}" if m.group(2) else "")
    caixa = f"{int(m.group(3)):04d}"
    doc = f"{int(m.group(4)):05d}"
    return f"PT/AHU/CU/{serie}/{caixa}/{doc}"


def _indice_resgate_por_bib(dados) -> dict[str, list[int]]:
    """Lista ordenada de `pagfis` conhecidos em cada rolo `bib` (só início conhecido)."""
    cache_bib = getattr(dados, "_indice_resgate_bib", None)
    if cache_bib is not None:
        return cache_bib
    por_bib: dict[str, set[int]] = {}
    if "resgate_docreader" in dados.documentos.columns:
        for val in dados.documentos["resgate_docreader"].dropna():
            texto = str(val).strip()
            if "#" not in texto:
                continue
            bib, pag = texto.split("#", 1)
            if bib and pag.isdigit():
                por_bib.setdefault(bib, set()).add(int(pag))
    ordenado = {bib: sorted(pags) for bib, pags in por_bib.items()}
    object.__setattr__(dados, "_indice_resgate_bib", ordenado)
    return ordenado


def _info_resgate(dados, doc_uid: str) -> dict[str, str | int | None]:
    linha = dados.documentos.iloc[dados.indice_de(doc_uid)]
    raw = linha.get("resgate_docreader") if "resgate_docreader" in linha.index else None
    if raw is None or pd.isna(raw) or "#" not in str(raw):
        return {
            "resgate_docreader": None,
            "resgate_bib": None,
            "resgate_pagfis": None,
            "resgate_proximo_pagfis": None,
        }
    texto = str(raw).strip()
    bib, pag = texto.split("#", 1)
    if not bib or not pag.isdigit():
        return {
            "resgate_docreader": texto,
            "resgate_bib": None,
            "resgate_pagfis": None,
            "resgate_proximo_pagfis": None,
        }
    pagfis = int(pag)
    pags = _indice_resgate_por_bib(dados).get(bib, [])
    idx = bisect_right(pags, pagfis)
    proximo = pags[idx] if idx < len(pags) else None
    return {
        "resgate_docreader": texto,
        "resgate_bib": bib,
        "resgate_pagfis": pagfis,
        "resgate_proximo_pagfis": proximo,
    }


def _serializar_ficha(dados, doc_uid: str) -> dict:
    ficha = montar(dados, doc_uid)
    resgate_info = _info_resgate(dados, doc_uid)
    return {
        "doc_uid": ficha.doc_uid,
        "colecao": ficha.colecao,
        "titulo": ficha.titulo,
        "ano": ficha.ano,
        "tipologia": ficha.tipologia,
        "tipologia_a_revisar": ficha.tipologia_a_revisar,
        "pasta": ficha.pasta,
        "resumo": ficha.resumo,
        "resumo_en": ficha.resumo_en,
        "resumo_en_fonte": ("MAPE dataset v4, doi:10.5281/zenodo.15481608, CC BY 4.0"
                            if ficha.resumo_en else None),
        "cotas": ficha.cotas,
        "links": {
            "catalogo": f"/ahu/doc/{ficha.doc_uid}",
            **ficha.links,
            **resgate_info,
        },
    }

@router.get("/saude", name="saude")
def saude():
    dados = main_module.dados_app
    if not dados:
        raise HTTPException(status_code=503, detail="Dados não carregados")
    manifesto = getattr(dados, "manifesto", {}) or {}
    return {"status": "ok", "documentos": len(dados.documentos),
            "versao": manifesto.get("versao_artefatos", "desconhecida"),
            "gerado_em": manifesto.get("gerado_em"),
            "commit": (manifesto.get("processo") or {}).get("commit")}

@router.get("/api/busca", name="api_busca")
def api_busca(request: Request):
    dados = main_module.dados_app
    consulta = parse_consulta(request)
    resposta, _, _ = cache.buscar(dados, consulta, encoder=main_module.encoder_app,
                                  reranker=main_module.reranker_app)

    resultados = []
    for r in resposta.pagina(consulta.pagina, 25):
        linha = dados.documentos.iloc[r.linha]
        resultados.append({
            "doc_uid": r.doc_uid,
            "cota": str(linha.get("reference_code") or linha.get("new_code") or linha.get("old_code")),
            "ano": int(linha["ano_isolado"]) if pd.notna(linha.get("ano_isolado")) else None,
            "posicao": r.posicao
        })

    return {
        "total": resposta.total,
        "pagina": consulta.pagina,
        "resultados": resultados
    }

@router.get("/api/doc/{doc_uid}", name="api_doc")
def api_doc(doc_uid: str):
    dados = main_module.dados_app
    try:
        return _serializar_ficha(dados, dados.uid_atual(doc_uid))
    except KeyError:
        raise HTTPException(status_code=404, detail="Documento não encontrado")


@router.get("/api/cota", name="api_cota")
def api_cota(cota: str = ""):
    dados = main_module.dados_app
    normalizada = _normalizar_cota_entrada(cota)
    chave = chave_cota(normalizada)
    if not chave:
        raise HTTPException(status_code=400, detail="Cota AHU não reconhecida")

    linhas = tabela_de_cotas(dados).get(chave, [])
    if not linhas:
        raise HTTPException(status_code=404, detail="Documento não encontrado no catálogo")

    correspondencias = [str(dados.documentos.iloc[i]["doc_uid"]) for i in linhas]
    return {
        "cota_consultada": cota.strip(),
        "chave_cota": chave,
        "total": len(correspondencias),
        "correspondencias": correspondencias,
        "documento": _serializar_ficha(dados, correspondencias[0]),
    }
