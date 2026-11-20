import pandas as pd
from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse

import web.main as main_module
from ahu.consulta import sem_duplicatas
from ahu.conversor import converter, converter_lista, tabela_da_cifra
from ahu.lista_ahu import pdf_da_selecao
from ahu.selecao import Selecao, maximo_na_url
from web import cache
from web.core import COOKIE_SELECAO, selecao_do_pedido, templates

router = APIRouter()


def linha_do_tempo(dados) -> dict:
    """Documentos por década no catálogo inteiro, para o gráfico da aba Sobre.

    O eixo vai da primeira à última década com peso: as poucas datas muito fora (erros de
    leitura do ano, documentos soltos) entram na conta de `fora`, e não esticam o gráfico.
    """
    visiveis = sem_duplicatas(dados, None)
    docs = dados.documentos if visiveis is None else dados.documentos[visiveis]
    anos = pd.to_numeric(docs["ano_isolado"], errors="coerce")
    com_data = anos.dropna().astype(int)
    if com_data.empty:
        return {"decadas": [], "total": len(docs), "sem_data": int(anos.isna().sum()), "fora": 0,
                "maximo": 0, "teto": 0}
    inicio = int(com_data.quantile(0.002)) // 10 * 10
    fim = int(com_data.quantile(0.998)) // 10 * 10
    contagem = (com_data // 10 * 10).value_counts()
    decadas = [(d, int(contagem.get(d, 0))) for d in range(inicio, fim + 10, 10)]
    dentro = sum(n for _, n in decadas)
    maximo = max(n for _, n in decadas)
    # O teto do eixo: o primeiro número "redondo" (1, 2, 3, 4, 5 ou 8 vezes uma potência de dez)
    # acima da maior barra, para as quatro linhas de grade caírem em valores legíveis.
    potencia = 10 ** max(0, len(str(maximo)) - 1)
    teto = next(f * potencia for f in (1, 2, 3, 4, 5, 8, 10) if f * potencia >= maximo)
    return {"decadas": decadas, "total": len(docs), "sem_data": int(anos.isna().sum()),
            "fora": int(len(com_data) - dentro), "maximo": maximo, "teto": int(teto),
            "inicio": inicio, "fim": fim + 9}


@router.get("/conversor", name="conversor")
def conversor(request: Request, q: str = "", lote: str = ""):
    dados = main_module.dados_app
    conversoes = []
    if q:
        conversoes = converter(q, dados)
    elif lote:
        conversoes = converter_lista(lote, dados)
    cifra = tabela_da_cifra().to_dict("records")
    return templates.TemplateResponse(request, "conversor.html", {
        "q": q, "lote": lote, "conversoes": conversoes, "cifra": cifra
    })


def get_selecao(request: Request, dados) -> Selecao:
    return selecao_do_pedido(request, dados)


def _gravar_selecao(response, sel: Selecao, dados) -> None:
    response.set_cookie(COOKIE_SELECAO, sel.para_url(dados) or "", max_age=31536000, path="/")


def _resposta_da_selecao(request: Request, dados, sel: Selecao, doc_uid: str, aviso: str = ""):
    """O que muda na tela quando a seleção muda: o botão do documento, a gaveta e o número da aba.

    Os três vêm no mesmo pedaço de HTML; o HTMX troca o botão clicado e leva os outros dois ao
    lugar pelo `id` (hx-swap-oob).
    """
    response = templates.TemplateResponse(request, "_selecao_mudou.html", {
        "uid": doc_uid,
        "marcado": doc_uid in sel,
        "botao_fora": request.query_params.get("de") == "gaveta",
        "linhas_selecao": sel.linhas(dados),
        "total_selecao": len(sel),
        "aviso_selecao": aviso,
    })
    _gravar_selecao(response, sel, dados)
    return response


@router.get("/selecao", name="selecao")
def selecao(request: Request):
    dados = main_module.dados_app
    sel = get_selecao(request, dados)
    linhas = sel.linhas(dados)
    return templates.TemplateResponse(request, "selecao.html", {
        "linhas": linhas, "total": len(sel), "maximo": maximo_na_url(dados)})


@router.post("/selecao/adicionar/{doc_uid}", name="adicionar_selecao")
def adicionar_selecao(request: Request, doc_uid: str):
    dados = main_module.dados_app
    sel = get_selecao(request, dados)
    aviso = ""
    if doc_uid not in sel and len(sel) >= 100:
        aviso = (f"A seleção atingiu o limite de {len(sel)} documentos. Baixe a lista em PDF e esvazie "
                 "a seleção para continuar.")
        return _resposta_da_selecao(request, dados, sel, doc_uid, aviso)
    sobraram = sel.adicionar(doc_uid)
    if sobraram or sel.para_url(dados) is None:
        # A seleção viaja no cookie do navegador, e ele tem um teto. Passou do teto, o documento
        # não entra — antes isto apagava a seleção inteira sem avisar.
        sel.remover(doc_uid)
        aviso = (f"A seleção está cheia ({len(sel)} documentos). Baixe a lista em PDF e esvazie "
                 "a seleção para continuar.")
    return _resposta_da_selecao(request, dados, sel, doc_uid, aviso)


@router.post("/selecao/remover/{doc_uid}", name="remover_selecao")
def remover_selecao(request: Request, doc_uid: str):
    dados = main_module.dados_app
    sel = get_selecao(request, dados)
    sel.remover(doc_uid)
    if request.query_params.get("volta") == "1":
        # Pedido da página Seleção, por formulário comum: volta a ela já sem o documento.
        response = RedirectResponse(url=request.url_for("selecao"), status_code=303)
        _gravar_selecao(response, sel, dados)
        return response
    return _resposta_da_selecao(request, dados, sel, doc_uid)


@router.post("/selecao/limpar", name="limpar_selecao")
def limpar_selecao(request: Request):
    destino = request.url_for("busca") if request.query_params.get("volta") == "busca" \
        else request.url_for("selecao")
    response = RedirectResponse(url=destino, status_code=303)
    response.set_cookie(COOKIE_SELECAO, "", max_age=0, path="/")
    return response


MAX_DOCS_PDF = 100


@router.get("/selecao/pdf", name="selecao_pdf")
def selecao_pdf(request: Request):
    dados = main_module.dados_app
    sel = get_selecao(request, dados)
    if len(sel) > MAX_DOCS_PDF:
        return Response(
            content=f"Máximo de {MAX_DOCS_PDF} documentos por PDF.".encode("utf-8"),
            status_code=400,
            media_type="text/plain; charset=utf-8",
        )
    pdf_bytes = pdf_da_selecao(dados, sel)
    return Response(content=pdf_bytes, media_type="application/pdf", headers={
        "Content-Disposition": "attachment; filename=lista_consulta_AHU.pdf"
    })


# Seções que saíram do catálogo público. Um link antigo para elas cai numa página que explica a
# mudança e leva à busca, em vez de um erro.
SECOES_RETIRADAS = ("/pessoas", "/pessoa/{resto:path}", "/amostras", "/amostras/plano", "/painel")


def secao_retirada(request: Request):
    return templates.TemplateResponse(request, "retirada.html", {}, status_code=410)


for _caminho in SECOES_RETIRADAS:
    router.add_api_route(_caminho, secao_retirada, methods=["GET"], include_in_schema=False)


@router.get("/sobre", name="sobre")
def sobre(request: Request):
    dados = main_module.dados_app
    linha = cache.por_dados(dados, "linha_do_tempo", lambda: linha_do_tempo(dados))
    docs = dados.documentos
    com_en = int(docs["resumo_en"].notna().sum()) if "resumo_en" in docs.columns else 0
    return templates.TemplateResponse(request, "sobre.html", {"linha": linha, "com_en": com_en})


@router.get("/referencias", name="referencias")
def referencias(request: Request):
    return templates.TemplateResponse(request, "referencias.html", {})
