"""O freio das buscas (web/limite.py)."""
import asyncio

from fastapi.testclient import TestClient
from starlette.responses import PlainTextResponse

from web.limite import LimiteDeBuscas
from web.main import criar_app


def test_limite_por_visitante(corpus_busca, monkeypatch):
    monkeypatch.setenv("AHU_LIMITE_POR_MINUTO", "3")
    client = TestClient(criar_app(dados_injetados=corpus_busca))
    for _ in range(3):
        assert client.get("/busca?q=governador&v=2").status_code == 200
    bloqueado = client.get("/busca?q=governador&v=2")
    assert bloqueado.status_code == 429
    assert bloqueado.headers["retry-after"] == "60"
    # Outro visitante (o Worker manda o IP real) continua buscando.
    outro = client.get("/busca?q=governador&v=2", headers={"X-Visitante-IP": "203.0.113.9"})
    assert outro.status_code == 200
    # Páginas que não buscam nunca são freadas.
    assert client.get("/sobre").status_code == 200
    assert client.get("/busca").status_code == 200
    assert client.get("/saude").status_code == 200


def test_limite_com_prefixo_ahu(corpus_busca, monkeypatch):
    monkeypatch.setenv("AHU_ROOT_PATH", "/ahu")
    monkeypatch.setenv("AHU_LIMITE_POR_MINUTO", "1")
    client = TestClient(criar_app(dados_injetados=corpus_busca))
    assert client.get("/ahu/api/busca?q=governador").status_code == 200
    assert client.get("/ahu/api/busca?q=governador").status_code == 429


def test_limite_desligado(corpus_busca, monkeypatch):
    monkeypatch.setenv("AHU_LIMITE", "0")
    monkeypatch.setenv("AHU_LIMITE_POR_MINUTO", "1")
    client = TestClient(criar_app(dados_injetados=corpus_busca))
    for _ in range(3):
        assert client.get("/api/busca?q=governador").status_code == 200


def test_janela_de_um_minuto():
    agora = [0.0]
    freio = LimiteDeBuscas(PlainTextResponse("ok"), por_minuto=2, relogio=lambda: agora[0])
    assert freio._dentro_do_limite("a") and freio._dentro_do_limite("a")
    assert not freio._dentro_do_limite("a")
    agora[0] = 61.0
    assert freio._dentro_do_limite("a")


def test_fila_cheia_recusa():
    """Com uma busca rodando e a fila cheia, o pedido seguinte volta na hora com 429."""
    liberar = asyncio.Event()

    async def lento(scope, receive, send):
        await liberar.wait()
        await PlainTextResponse("ok")(scope, receive, send)

    freio = LimiteDeBuscas(lento, por_minuto=100, simultaneas=1, fila=0, espera=5)
    escopo = {"type": "http", "path": "/api/busca", "root_path": "", "query_string": b"q=x",
              "headers": [], "client": ("1.2.3.4", 1), "method": "GET"}

    async def cenario():
        enviados = {1: [], 2: []}

        async def receber():
            return {"type": "http.request", "body": b""}

        def enviar(n):
            async def _enviar(msg):
                enviados[n].append(msg)
            return _enviar

        primeira = asyncio.create_task(freio(dict(escopo), receber, enviar(1)))
        await asyncio.sleep(0)
        await freio(dict(escopo), receber, enviar(2))
        liberar.set()
        await primeira
        return enviados

    enviados = asyncio.run(cenario())
    assert enviados[2][0]["status"] == 429
    assert enviados[1][0]["status"] == 200
