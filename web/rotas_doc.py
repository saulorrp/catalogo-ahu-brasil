from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

import web.main as main_module
from ahu.ficha import montar
from web.core import selecao_do_pedido, templates

router = APIRouter()

@router.get("/doc/{doc_uid}", name="doc")
def doc(request: Request, doc_uid: str, q: str = ""):
    dados = main_module.dados_app
    atual = dados.uid_atual(doc_uid)
    if atual != doc_uid:
        # Um uid de versão antiga do catálogo: o documento é o mesmo, com o uid de hoje.
        destino = request.url_for("doc", doc_uid=atual)
        return RedirectResponse(url=f"{destino}?q={q}" if q else str(destino), status_code=301)
    try:
        termos = q.split() if q else []
        ficha = montar(dados, doc_uid, termos)
    except KeyError:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    return templates.TemplateResponse(request, "doc.html", {
        "ficha": ficha,
        "marcado": doc_uid in selecao_do_pedido(request, dados),
    })
