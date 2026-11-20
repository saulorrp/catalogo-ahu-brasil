"""consulta.py — o objeto `Consulta`, com ida e volta para dicionário e para a URL.

`Consulta` é o objeto central do app: texto, modo, rigor, filtros, ordenação e página. A
**mesma** estrutura vai para dois lugares:

* a **URL**, compacta e versionada, para o "Copiar link desta busca";
* o **bloco de proveniência** do PDF exportado, em forma legível.

Duas regras que a ida e volta tem de respeitar:

1. o que estava no padrão não vai para a URL — um link de busca não carrega estado morto;
2. o que vai, volta igual. `de_url(para_url(c)) == c` para qualquer `Consulta`, e é isso que o
   teste cobre com buscas variadas.

A versão (`v=`) é o que permite mudar o formato depois sem quebrar links já copiados: uma URL
sem versão, ou com versão mais nova que a do app, é recusada com mensagem clara em vez de virar
silenciosamente outra busca.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

import pandas as pd

from ahu import busca
from ahu.filtros import Filtros

# Um link antigo que traga um parâmetro retirado continua abrindo: o `de_url` descarta só esse
# parâmetro e respeita todo o resto.
VERSAO_URL = 2
CHAVES_RETIRADAS = frozenset({"l", "fu", "fd", "fg", "fv", "fi", "s1", "s2", "fn", "fy", "fa", "s"})
ORDENACOES = ("relevancia", "ano_asc", "ano_desc")
TAMANHO_PAGINA = 25

# Chaves curtas da URL. Trocar qualquer uma delas exige subir VERSAO_URL.
CHAVES = {
    "texto": "q", "modo": "m", "rigor": "r", "pagina": "p", "ordenacao": "o",
}
CHAVES_FILTROS = {
    "colecoes": "fc", "ano_de": "a1", "ano_ate": "a2", "sem_data": "sd", "pastas": "fp",
    "tipologias": "ft",
}
SEPARADOR = "|"     # separa itens de uma lista dentro de um valor da URL


class ErroDeLink(ValueError):
    """Link de busca inválido: versão desconhecida ou valor fora do permitido."""


@dataclass
class Consulta:
    texto: str = ""
    modo: str = "automatico"
    rigor: str = "medio"
    filtros: Filtros = field(default_factory=Filtros)
    ordenacao: str = "relevancia"
    pagina: int = 1

    # -----------------------------------------------------------------
    def __post_init__(self) -> None:
        if isinstance(self.filtros, dict):
            self.filtros = Filtros(**self.filtros)
        self.validar()

    def validar(self) -> None:
        if self.modo not in busca.MODOS:
            raise ErroDeLink(f"Modo desconhecido: {self.modo!r}. Use um de {', '.join(busca.MODOS)}.")
        if self.rigor not in busca.RIGORES:
            raise ErroDeLink(
                f"Rigor desconhecido: {self.rigor!r}. Use um de {', '.join(busca.RIGORES)}."
            )
        if self.ordenacao not in ORDENACOES:
            raise ErroDeLink(
                f"Ordenação desconhecida: {self.ordenacao!r}. Use uma de {', '.join(ORDENACOES)}."
            )
        if self.pagina < 1:
            raise ErroDeLink(f"Página deve ser 1 ou mais, veio {self.pagina}.")

    # -----------------------------------------------------------------
    # Dicionário (proveniência do PDF)
    # -----------------------------------------------------------------
    def para_dicionario(self) -> dict:
        """Forma legível e completa, para o bloco de proveniência e para a capa do PDF."""
        return {
            "versao": VERSAO_URL,
            "texto": self.texto,
            "modo": self.modo,
            "rigor": self.rigor,
            "ordenacao": self.ordenacao,
            "pagina": self.pagina,
            "filtros": asdict(self.filtros),
            "filtros_ativos": self.filtros.ativos(),
        }

    @classmethod
    def de_dicionario(cls, dados: dict) -> "Consulta":
        versao = dados.get("versao", VERSAO_URL)
        # Uma proveniência mais antiga ainda se lê: os campos que saíram são descartados abaixo.
        if int(versao) > VERSAO_URL:
            raise ErroDeLink(
                f"Esta consulta foi gravada na versão {versao} e o app usa a {VERSAO_URL}."
            )
        conhecidos = {f.name for f in fields(cls)}
        argumentos = {k: v for k, v in dados.items() if k in conhecidos and k != "filtros"}
        # Filtros que o catálogo não tem mais são descartados; os outros valem.
        campos_de_filtro = {f.name for f in fields(Filtros)}
        filtros = {k: v for k, v in (dados.get("filtros") or {}).items() if k in campos_de_filtro}
        return cls(filtros=Filtros(**filtros), **argumentos)

    # -----------------------------------------------------------------
    # URL
    # -----------------------------------------------------------------
    def para_url(self) -> dict[str, str]:
        """Só o que difere do padrão, com as chaves curtas e a versão."""
        padrao = Consulta()
        saida: dict[str, str] = {"v": str(VERSAO_URL)}
        for campo, chave in CHAVES.items():
            valor = getattr(self, campo)
            if valor != getattr(padrao, campo) and valor is not None:
                saida[chave] = _texto_do_valor(valor)
        padrao_filtros = Filtros()
        for campo, chave in CHAVES_FILTROS.items():
            valor = getattr(self.filtros, campo)
            if valor != getattr(padrao_filtros, campo) and valor is not None:
                saida[chave] = _texto_do_valor(valor)
        return saida

    @classmethod
    def de_url(cls, parametros: dict[str, Any]) -> "Consulta":
        """Lê o que `para_url` escreveu. Uma URL vazia dá a consulta padrão."""
        bruto = {k: _primeiro(v) for k, v in dict(parametros or {}).items()}
        if not bruto:
            return cls()
        versao = bruto.get("v")
        if versao is None:
            raise ErroDeLink("Link de busca sem versão (falta `v`). Copie o link de novo.")
        try:
            versao = int(versao)
        except (TypeError, ValueError) as e:
            raise ErroDeLink(f"Versão do link inválida: {versao!r}.") from e
        if versao > VERSAO_URL:
            raise ErroDeLink(
                f"Este link foi feito na versão {versao} e o app usa a {VERSAO_URL}. "
                "Refaça a busca."
            )
        # Um link antigo pode trazer filtros que o catálogo não tem mais. Ele continua abrindo:
        # esses parâmetros são descartados e os outros valem.
        bruto = {k: v for k, v in bruto.items() if k not in CHAVES_RETIRADAS}

        padrao, padrao_filtros = cls(), Filtros()
        argumentos = {
            campo: _valor_do_texto(bruto[chave], getattr(padrao, campo), campo)
            for campo, chave in CHAVES.items() if chave in bruto
        }
        filtros = {
            campo: _valor_do_texto(bruto[chave], getattr(padrao_filtros, campo), campo)
            for campo, chave in CHAVES_FILTROS.items() if chave in bruto
        }
        usadas = {"v", *CHAVES.values(), *CHAVES_FILTROS.values()}
        sobrando = sorted(set(bruto) - usadas)
        if sobrando:
            raise ErroDeLink(f"Link com parâmetros desconhecidos: {', '.join(sobrando)}.")
        return cls(filtros=Filtros(**filtros), **argumentos)


# ---------------------------------------------------------------------------
# O link da busca
# ---------------------------------------------------------------------------

def para_query(consulta: Consulta) -> str:
    """A consulta como *query string*, com o `?` na frente: `?v=2&q=gado&m=exata`.

    É um link **relativo**, que vale em qualquer endereço onde o app esteja servido.
    """
    return "?" + urlencode(consulta.para_url())


def url_da_busca(consulta: Consulta, base: str | None = None) -> str:
    """O link do botão "Copiar link desta busca".

    Com `base` (o endereço da página), devolve a URL inteira,
    que é o que se cola num e-mail. Sem ela, devolve o link relativo — nada é inventado: o
    módulo não tem como saber em que domínio o app está.
    """
    query = urlencode(consulta.para_url())
    if not base:
        return "?" + query
    partes = urlsplit(base)
    return urlunsplit((partes.scheme, partes.netloc, partes.path or "/", query, ""))


def asdict_raso(consulta: Consulta) -> dict:
    """Campos da consulta sem desmontar os filtros (o `asdict` do dataclass desmontaria)."""
    return {f.name: getattr(consulta, f.name) for f in fields(consulta)}


# ---------------------------------------------------------------------------
# Serialização de valores
# ---------------------------------------------------------------------------

def _texto_do_valor(valor) -> str:
    if isinstance(valor, bool):
        return "1" if valor else "0"
    if isinstance(valor, list):
        return SEPARADOR.join(str(v) for v in valor)
    return str(valor)


def _valor_do_texto(texto: str, padrao, campo: str):
    if isinstance(padrao, bool):
        if texto not in ("0", "1"):
            raise ErroDeLink(f"O parâmetro {campo} deveria ser 0 ou 1, veio {texto!r}.")
        return texto == "1"
    if isinstance(padrao, list):
        return [p for p in texto.split(SEPARADOR) if p]
    if isinstance(padrao, int) or campo in ("ano_de", "ano_ate", "pagina"):
        try:
            return int(texto)
        except (TypeError, ValueError) as e:
            raise ErroDeLink(f"O parâmetro {campo} deveria ser um número, veio {texto!r}.") from e
    return texto


def _primeiro(valor):
    """`st.query_params` pode devolver lista quando a chave repete."""
    if isinstance(valor, (list, tuple)):
        return valor[0] if valor else ""
    return valor


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------

def sem_duplicatas(dados, filtro):
    """O filtro sem os verbetes repetidos (coluna `duplicata_de`, de corpus/duplicatas.ignore).
    Eles continuam nos dados, por transparência; só a busca não os devolve."""
    coluna = dados.documentos.get("duplicata_de")
    if coluna is None or not coluna.notna().any():
        return filtro
    fora = coluna.notna().to_numpy()
    return ~fora if filtro is None else (filtro & ~fora)


def executar(dados, consulta: Consulta, encoder=None, **extra) -> busca.Resposta:
    """Roda a busca da consulta já com os filtros aplicados, e ordena como ela pede."""
    resposta = busca.buscar(
        dados, consulta.texto, modo=consulta.modo, rigor=consulta.rigor, encoder=encoder,
        filtro=sem_duplicatas(dados, consulta.filtros.mascara(dados)), **extra,
    )
    if consulta.ordenacao != "relevancia":
        anos = dados.documentos["ano_isolado"]
        decrescente = consulta.ordenacao == "ano_desc"

        def chave(r):
            ano = anos.iloc[r.linha]
            # Documento sem data (186 deles) vai para o fim nas duas ordens.
            ausente = bool(pd.isna(ano))
            valor = 0 if ausente else int(ano)
            return (ausente, -valor if decrescente else valor, r.linha)

        resposta.resultados.sort(key=chave)
        for posicao, r in enumerate(resposta.resultados, start=1):
            r.posicao = posicao
    return resposta
