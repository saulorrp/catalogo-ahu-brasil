"""idioma.py — a interface em português (padrão) ou em inglês.

O idioma fica num cookie (`ahu-idioma`), trocado pelo seletor PT/EN do topo. Ele muda só a
interface e qual resumo vai à frente: com EN, a tradução do MAPE vira o texto principal e o resumo
do catálogo do AHU vai para a gaveta; sem tradução, fica o português. Os dados não mudam: nomes de
pastas e tipologias vêm dos dados e continuam em português, e a lista em PDF também.

Nos modelos (Jinja), `en` diz se a página está em inglês e `tr("português", "English")` escolhe o
texto. Frases que vêm prontas de `ahu/` (avisos da busca e do conversor, rótulos das cotas e dos
links) passam pelo filtro `en`, que as traduz quando a página está em inglês.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from fastapi import Request
from jinja2 import pass_context

COOKIE_IDIOMA = "ahu-idioma"
IDIOMAS = ("pt", "en")


def idioma(request: Request | None) -> str:
    if request is None:
        return "pt"
    valor = request.cookies.get(COOKIE_IDIOMA, "pt")
    return valor if valor in IDIOMAS else "pt"


def contexto(request: Request) -> dict:
    """Processador de contexto: toda página sabe se está em inglês."""
    return {"en": idioma(request) == "en"}


@pass_context
def tr(ctx, pt: str, en: str) -> str:
    return en if ctx.get("en") else pt


# Frases fixas que vêm de `ahu/` (rótulos, avisos). A chave é o texto português exato.
FRASES = {
    # cotas e links (ahu/ficha.py, ahu/links.py, ahu/conversor.py)
    "Código de referência": "Reference code",
    "Código atual": "Current code",
    "Cota impressa na fonte": "Shelfmark as printed in the source",
    "Código antigo": "Old code",
    "Item e data": "Item and date",
    "Caixa no DigitArq": "Box in DigitArq",
    "Ficha no DigitArq": "Record in DigitArq",
    "Códice no Projeto Resgate": "Codex in Projeto Resgate",
    "Imagem no Projeto Resgate": "Image in Projeto Resgate",
    "Portal do Projeto Resgate": "Projeto Resgate portal",
    # conversor: famílias e níveis
    "referencia": "reference code",
    "resgate": "current code",
    "antiga": "old code",
    "formatação": "formatting",
    "numeração igual": "identical numbering",
    "concordância da base": "the database concordance",
    "sem conversão": "no conversion",
    "sim, por formatação": "yes, by formatting",
    "só pela base": "only through the database",
    # avisos da busca (ahu/busca.py)
    "Nenhum documento muito próximo desta consulta; os resultados podem ser pouco relevantes.":
        "No document is very close to this query; the results may not be very relevant.",
    "A consulta só tem palavras muito comuns, que a busca ignora. A lista abaixo é o corpus com os "
    "filtros aplicados.":
        "The query has only very common words, which the search ignores. The list below is the "
        "whole catalogue with the filters applied.",
    # avisos do conversor (ahu/conversor.py)
    "Formato não reconhecido. Confira a digitação; sufixos (`doc. 1-A`, `cx. 9-A`) e códices (`n.v.`) "
    "ficam fora do conversor.":
        "Format not recognised. Check the spelling; suffixes (`doc. 1-A`, `cx. 9-A`) and codices "
        "(`n.v.`) are outside the converter.",
    "Código antigo tirado da base, não da formatação.":
        "Old code taken from the database, not from the formatting.",
    "Fora da base: o código antigo não é derivável desta série.":
        "Not in the database: the old code cannot be derived for this series.",
    "Código antigo: a numeração mudou na arrumação atual, e a conversão depende da base.":
        "Old code: the numbering changed in the current arrangement, and the conversion depends on "
        "the database.",
    "Sem conversão: esta cota antiga não está na base, e a numeração antiga não é derivável da "
    "atual. A concordância está no catálogo do Projeto Resgate.":
        "No conversion: this old shelfmark is not in the database, and the old numbering cannot be "
        "derived from the current one. The concordance is in the Projeto Resgate catalogue.",
}

# Frases com números ou nomes no meio: (padrão português, molde inglês).
MOLDES = [
    (re.compile(r"^A série (\S+) não está na cifra: a forma foi convertida, mas sem o nome do estado\.$"),
     r"Series \1 is not in the cipher: the form was converted, but without the name of the state."),
    (re.compile(r"^Série completada com zeros: (\S+)\.$"), r"Series padded with zeros: \1."),
    (re.compile(r"^Intervalo de (\d+) documentos: o código de referência guarda só o primeiro\.$"),
     r"Range of \1 documents: the reference code keeps only the first."),
    (re.compile(r"^(\d+) de (\d+) documentos atuais com esta cota antiga\.$"),
     r"\1 of \2 current documents with this old shelfmark."),
    (re.compile(r"^O link abre na primeira página do códice; o documento está no fl\. (.+)\.$"),
     r"The link opens on the first page of the codex; the document is on fol. \1."),
    (re.compile(r"^O link abre na primeira página do códice; procure o fólio do documento\.$"),
     r"The link opens on the first page of the codex; look for the document's folio."),
    (re.compile(r"^A seleção atingiu o limite de (\d+) documentos\. Baixe a lista em PDF e esvazie a "
                r"seleção para continuar\.$"),
     r"The selection has reached its limit of \1 documents. Download the PDF list and empty the "
     r"selection to continue."),
    (re.compile(r"^A seleção está cheia \((\d+) documentos\)\. Baixe a lista em PDF e esvazie a "
                r"seleção para continuar\.$"),
     r"The selection is full (\1 documents). Download the PDF list and empty the selection to "
     r"continue."),
]


def traduzir(texto) -> str:
    """O texto em inglês, se for uma frase conhecida; senão, o próprio texto."""
    if texto is None:
        return ""
    texto = str(texto)
    if texto in FRASES:
        return FRASES[texto]
    for padrao, molde in MOLDES:
        if padrao.match(texto):
            return padrao.sub(molde, texto)
    return texto


@pass_context
def filtro_en(ctx, texto) -> str:
    """`{{ rotulo | en }}`: traduz uma frase de `ahu/` quando a página está em inglês."""
    return traduzir(texto) if ctx.get("en") else ("" if texto is None else str(texto))


def volta_segura(request: Request) -> str | None:
    """O caminho da página de onde a pessoa veio (só caminho e query, nunca outro site).

    Vem de `?volta=` (um caminho) ou do cabeçalho Referer (um endereço inteiro, do qual só o caminho
    é aproveitado: atrás do Worker da Cloudflare o domínio é outro, mas o caminho é o mesmo).
    """
    volta = request.query_params.get("volta")
    if volta is not None:
        if not volta.startswith("/") or volta.startswith("//") or "\\" in volta:
            return None
        partes = urlsplit(volta)
    else:
        partes = urlsplit(request.headers.get("referer") or "")
    caminho = partes.path or ""
    if not caminho.startswith("/") or caminho.startswith("//") or "\\" in caminho:
        return None
    return caminho + (f"?{partes.query}" if partes.query else "")
