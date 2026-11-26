"""limite.py — o freio das buscas.

Uma busca nova custa ao servidor de 2 a 3 segundos de processador (e5, BM25 e reranker), e o
servidor é um Mac mini doméstico que hospeda outros serviços. Sem freio, algumas dezenas de buscas
simultâneas, de um robô ou de alguém mal-intencionado, ocupam a máquina inteira. O freio tem duas
partes, ambas só nos pedidos que fazem busca (`ROTAS_CARAS`); fichas, páginas fixas e arquivos
estáticos passam sempre:

1. **Por visitante:** no máximo `AHU_LIMITE_POR_MINUTO` pedidos de busca por minuto (padrão 60).
   Cada busca na tela faz dois pedidos (a lista e a releitura do reranker), então 60 são 30
   buscas por minuto, muito acima do ritmo de quem lê os resultados. Acima disso: 429.
2. **No total:** no máximo `AHU_BUSCAS_SIMULTANEAS` buscas rodando ao mesmo tempo (padrão 2). As
   seguintes esperam numa fila de até `AHU_FILA_MAXIMA` pedidos (padrão 20), por até
   `AHU_ESPERA_MAXIMA` segundos (padrão 15). Fila cheia ou espera esgotada: também 429, e não 503,
   porque o Worker da Cloudflare troca 502–504 pela página "fora do ar". Esta parte é a que
   protege a máquina mesmo de quem troca de IP a cada pedido.

O visitante é reconhecido pelo cabeçalho `X-Visitante-IP`, que o Worker da Cloudflare preenche com
o IP real; na falta dele, pelo `CF-Connecting-IP`, pelo primeiro IP de `X-Forwarded-For` ou pelo
endereço da conexão. Nada disso é gravado: as contagens vivem na memória do processo e somem com
ele. `AHU_LIMITE=0` desliga o freio (útil em testes locais).
"""
from __future__ import annotations

import asyncio
import os
import time
from collections import deque

from starlette.responses import HTMLResponse
from starlette.types import ASGIApp, Receive, Scope, Send

# Os caminhos (depois do prefixo `/ahu`) que disparam uma busca.
ROTAS_CARAS = {"/", "/busca", "/resultados", "/api/busca", "/selecao/pdf"}

# Limpeza da tabela de visitantes, para que ela não cresça sem fim.
MAXIMO_DE_VISITANTES = 10_000

JANELA = 60.0   # segundos


def _int_do_ambiente(nome: str, padrao: int) -> int:
    try:
        return int(os.environ.get(nome, "").strip() or padrao)
    except ValueError:
        return padrao


def ligado() -> bool:
    return os.environ.get("AHU_LIMITE", "1").strip().lower() not in ("0", "nao", "não", "false")


def _pagina(titulo: str, texto: str, status: int, espera: int) -> HTMLResponse:
    html = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{titulo}</title>
<style>body{{font-family:Georgia,serif;background:#f3ead8;color:#2b2420;max-width:36rem;
margin:15vh auto;padding:0 16px;line-height:1.6}}h1{{font-weight:400;color:#800000}}</style>
</head><body><h1>{titulo}</h1><p>{texto}</p>
<p lang="en">Too many searches at once. Please wait a few seconds and try again.</p>
</body></html>"""
    return HTMLResponse(html, status_code=status, headers={"Retry-After": str(espera),
                                                           "Cache-Control": "no-store"})


class LimiteDeBuscas:
    """Middleware ASGI: conta e enfileira só os pedidos que fazem busca."""

    def __init__(self, app: ASGIApp, por_minuto: int | None = None,
                 simultaneas: int | None = None, fila: int | None = None,
                 espera: float | None = None, relogio=time.monotonic):
        self.app = app
        self.por_minuto = por_minuto or _int_do_ambiente("AHU_LIMITE_POR_MINUTO", 60)
        self.simultaneas = simultaneas or _int_do_ambiente("AHU_BUSCAS_SIMULTANEAS", 2)
        self.fila_maxima = fila if fila is not None else _int_do_ambiente("AHU_FILA_MAXIMA", 20)
        self.espera = espera or float(_int_do_ambiente("AHU_ESPERA_MAXIMA", 15))
        self.relogio = relogio
        self._visitantes: dict[str, deque] = {}
        self._semaforo: asyncio.Semaphore | None = None
        self._na_fila = 0

    # -----------------------------------------------------------------
    @staticmethod
    def _caminho(scope: Scope) -> str:
        caminho = scope.get("path", "")
        raiz = scope.get("root_path", "")
        if raiz and caminho.startswith(raiz):
            caminho = caminho[len(raiz):]
        return caminho or "/"

    @staticmethod
    def _faz_busca(scope: Scope) -> bool:
        caminho = LimiteDeBuscas._caminho(scope)
        if caminho not in ROTAS_CARAS:
            return False
        if caminho in ("/", "/busca"):
            # A página inicial sem texto é a mesma para todos e fica na memória do app.
            from urllib.parse import parse_qs
            query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
            return any(v.strip() for v in query.get("q", []))
        return True

    @staticmethod
    def visitante(scope: Scope) -> str:
        cabecalhos = {k.decode("latin-1").lower(): v.decode("latin-1")
                      for k, v in scope.get("headers", [])}
        for nome in ("x-visitante-ip", "cf-connecting-ip"):
            if cabecalhos.get(nome, "").strip():
                return cabecalhos[nome].strip()[:64]
        encaminhado = cabecalhos.get("x-forwarded-for", "").split(",")[0].strip()
        if encaminhado:
            return encaminhado[:64]
        cliente = scope.get("client")
        return cliente[0] if cliente else "desconhecido"

    def _dentro_do_limite(self, quem: str) -> bool:
        agora = self.relogio()
        if len(self._visitantes) > MAXIMO_DE_VISITANTES:
            self._visitantes = {k: v for k, v in self._visitantes.items()
                                if v and agora - v[-1] < JANELA}
        marcas = self._visitantes.setdefault(quem, deque())
        while marcas and agora - marcas[0] >= JANELA:
            marcas.popleft()
        if len(marcas) >= self.por_minuto:
            return False
        marcas.append(agora)
        return True

    # -----------------------------------------------------------------
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._faz_busca(scope):
            await self.app(scope, receive, send)
            return

        if not self._dentro_do_limite(self.visitante(scope)):
            resposta = _pagina("Muitas buscas seguidas",
                               "Você fez muitas buscas em pouco tempo. Espere um minuto e tente "
                               "de novo.", 429, int(JANELA))
            await resposta(scope, receive, send)
            return

        if self._semaforo is None:
            self._semaforo = asyncio.Semaphore(self.simultaneas)
        if self._semaforo.locked() and self._na_fila >= self.fila_maxima:
            await self._ocupado(scope, receive, send)
            return
        self._na_fila += 1
        try:
            await asyncio.wait_for(self._semaforo.acquire(), timeout=self.espera)
        except asyncio.TimeoutError:
            await self._ocupado(scope, receive, send)
            return
        finally:
            self._na_fila -= 1
        try:
            await self.app(scope, receive, send)
        finally:
            self._semaforo.release()

    async def _ocupado(self, scope: Scope, receive: Receive, send: Send) -> None:
        resposta = _pagina("O catálogo está ocupado",
                           "Há muitas buscas sendo feitas agora. Espere alguns segundos e tente "
                           "de novo.", 429, 10)
        await resposta(scope, receive, send)
