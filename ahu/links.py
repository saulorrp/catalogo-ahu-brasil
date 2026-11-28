"""links.py — links para os acervos oficiais e para o "Reportar erro".

Dois destinos:

* **DigitArq** (Arquivo Nacional da Torre do Tombo / ANTT): a busca aceita o `reference_code`
  (`PT/AHU/CU/021/0006/00390`) e leva à ficha de controle arquivístico.
* **Projeto Resgate** (Biblioteca Nacional): o DocReader da BN não tem busca por cota (os
  documentos são imagens de manuscrito, sem texto), mas abre num quadro dado:
  `DocReader.aspx?bib=<rolo>&pagfis=<quadro>`. As páginas de verbetes do gov.br ligam cada número a
  esse quadro, e a coluna `resgate_docreader` (`021_SC#37`, do `build/cotas.py`) o guarda. Com
  ela o link abre a imagem do documento; sem ela, o link vai ao portal e o `new_code` é oferecido
  para copiar. Rio de Janeiro, São Paulo, Sacramento e Brasil Geral, cujos catálogos não estão em
  HTML, ganharam o quadro pela varredura do próprio DocReader (`coleta/scripts/varrer_docreader.py`).
  O servidor da BN recusa acessos de fora do Brasil.

E um terceiro: o **"Reportar erro"**, um e-mail já preenchido com o documento e a página.

Nada aqui depende de rede: são só URLs montadas.

**`referencia_crav`** é a conversão de cota em código de referência: ela aceita as duas famílias
de cota (Resgate e referência) e devolve sempre `PT/AHU/CU/<série>/<caixa>/<documento>`, com os
zeros à esquerda. A regra mora em `ahu/conversor.py`, e esta função só a chama. Ela **não** é a
`busca.chave_cota`, e a diferença importa: a `chave_cota` é uma chave de *lookup* dentro do
corpus, que joga os zeros fora para poder casar as três grafias; esta monta o código oficial que o
DigitArq entende e que vai impresso na lista de consulta.
"""
from __future__ import annotations

import os
import re
from urllib.parse import quote, urlencode

DIGITARQ = "https://digitarq.arquivos.pt/search?query={cota}&isAdvancedSearch=false"
# A raiz do domínio não abre nada útil; o portal que a BN divulga é o docmulti do DocReader.
RESGATE = "https://resgate.bn.gov.br/docreader/docmulti.aspx?bib=resgate"
# O domínio antigo (resgate.bn.br, que as páginas de verbetes do gov.br ainda usam) hoje resolve
# num servidor de redirecionamento da BN (redirect-bn-br.bn.br), e o link não abria. O portal já
# está em resgate.bn.gov.br; o `hf` diz ao DocReader em que host ele está, como nas páginas do gov.br.
DOCREADER = ("https://resgate.bn.gov.br/docreader/DocReader.aspx"
             "?bib={bib}&hf=resgate.bn.gov.br&pagfis={pagfis}")


def limpar_cota(texto) -> str:
    """A cota como se imprime: sem a pontuação solta que o catálogo deixa no fim.

    O catálogo traz `AHU_ACL_CU_003, Cx. 4, D. 360.]` e `… D. 390.`; o ponto e o colchete são
    resto de extração, e na folha que vai ao arquivo eles só confundem quem procura a cota.
    """
    import pandas as pd

    if texto is None or (not isinstance(texto, str) and pd.isna(texto)):
        return ""
    return str(texto).strip().rstrip(" .];,")


def referencia_crav(texto: str | None) -> str | None:
    """Converte uma cota no código de referência: `PT/AHU/CU/005/0135/10451`.

    A regra é a do `ahu.conversor` (níveis 1 e 2): aceita a referência, a cota do Resgate e as
    cotas antigas de numeração igual (Castro e Almeida, Mendes Gouveia). Devolve None quando o
    texto não contém uma cota assim — o caso do `UNFORMATTED_CODE` e das cotas antigas comuns
    (`AHU-São Paulo, cx. 26, doc. 8`), cuja numeração não é a atual e por isso não tem código
    CRAV derivável.
    """
    if not texto:
        return None
    from ahu.conversor import para_referencia, reconhecer

    cota = reconhecer(str(texto))
    return para_referencia(cota) if cota else None

# "Reportar erro" abre o e-mail do leitor, endereçado ao autor: quem lê o catálogo raramente tem
# conta no GitHub. `AHU_EMAIL_ERRO` deixa um fork trocar o endereço, e
# `AHU_URL_PUBLICA` é o endereço do app citado na mensagem.
# `AHU_ANONIMO=1` é o modo de avaliação cega (pareceristas de um artigo sobre o catálogo): o site
# não mostra o nome do autor nem links que o identifiquem, e o e-mail sai sem destinatário e sem o
# endereço público, a menos que `AHU_EMAIL_ERRO` e `AHU_URL_PUBLICA` sejam dados explicitamente.
ANONIMO = os.environ.get("AHU_ANONIMO", "").strip().lower() in {"1", "true", "sim", "yes"}
EMAIL_ERRO = os.environ.get("AHU_EMAIL_ERRO", "" if ANONIMO else "saulorrp@gmail.com")
URL_PUBLICA = os.environ.get(
    "AHU_URL_PUBLICA", "" if ANONIMO else "https://catalogo-ahu.saulo-r.workers.dev/ahu").rstrip("/")


def _email(assunto: str, linhas: list[str], destino: str | None = None) -> str:
    """Um `mailto:` com assunto e corpo, codificados com %20 (o `+` não vira espaço em `mailto:`)."""
    return f"mailto:{destino or EMAIL_ERRO}?" + urlencode(
        {"subject": assunto, "body": "\n".join(linhas)}, quote_via=quote)


def email_de_documento(doc_uid: str, cota: str | None = None, titulo: str | None = None,
                       destino: str | None = None) -> str:
    """"Reportar erro" de um documento: o e-mail já diz qual documento é e onde ele está no app."""
    rotulo = cota or doc_uid
    return _email(f"Catálogo AHU: erro no documento {rotulo}", [
        "Olá,",
        "",
        "Encontrei um erro neste documento do Catálogo AHU:",
        "",
        f"Cota: {cota or '—'}",
        f"Título: {titulo or '—'}",
        f"Identificador: {doc_uid}",
        *([f"Página: {URL_PUBLICA}/doc/{doc_uid}"] if URL_PUBLICA else []),
        "",
        "O que está errado:",
        "",
        "",
        "Qual seria o dado correto (e a fonte, se houver):",
        "",
    ], destino)


def digitarq(cota: str | None) -> str | None:
    """Busca no DigitArq pelo código de referência. None quando não há cota reconhecível.

    Aceita qualquer das duas famílias de cota e normaliza pela `referencia_crav`: é o que faz o
    link funcionar também para os documentos cujo `reference_code` é `UNFORMATTED_CODE` mas cujo
    `new_code` do Resgate está inteiro.
    """
    referencia = referencia_crav(cota)
    if referencia is None:
        return None
    return DIGITARQ.format(cota=quote(referencia, safe=""))


def resgate(docreader: str | None = None) -> str:
    """A imagem do documento no DocReader do Resgate (`docreader` = `rolo#quadro`), ou o portal."""
    if docreader and "#" in docreader:
        bib, pagfis = docreader.split("#", 1)
        if bib and pagfis.isdigit():
            return DOCREADER.format(bib=quote(bib, safe=""), pagfis=pagfis)
    return RESGATE


def _valor(documento, campo):
    import pandas as pd

    v = documento.get(campo) if hasattr(documento, "get") else None
    return None if v is None or (not isinstance(v, str) and pd.isna(v)) else str(v)


AVISO_COTA_RECONSTRUIDA = (
    "Cota não oficial: a fonte não traz a cota AHU deste documento, e a cota mostrada foi montada "
    "pelo catálogo a partir da numeração do inventário. Por isso não há link de acesso.")


def cota_reconstruida(documento) -> bool:
    """Se a cota do documento foi montada pelo catálogo (`corpus/cotas_reconstruidas.ignore`).

    Essa cota não é a do AHU e leva ao documento errado: nenhum link sai dela.
    """
    v = documento.get("cota_reconstruida") if hasattr(documento, "get") else None
    try:
        return bool(v) and v == v  # NaN e pd.NA não contam
    except TypeError:
        return False


def digitarq_do_documento(documento) -> tuple[str | None, bool]:
    """(link do DigitArq, se o link é só da caixa) para uma linha de `documentos.parquet`.

    O DigitArq descreve muitos documentos em intervalo, e o intervalo dele nem sempre começa onde
    começa o do catálogo; aí a busca pela referência do documento volta vazia. Por isso o link vai,
    nesta ordem, ao `referencia_digitarq` (o registro do DigitArq que contém o documento, posto
    pelo `build/cotas.py`); à busca pela caixa, quando o índice foi consultado e não achou registro;
    e à busca pela referência, quando a base não traz a coluna. A cota do Resgate entra como
    reserva: há documentos com `UNFORMATTED_CODE` no `reference_code` e um `new_code` inteiro.
    """
    if cota_reconstruida(documento):
        return None, False
    registro = _valor(documento, "referencia_digitarq")
    if registro:
        return DIGITARQ.format(cota=quote(registro, safe="")), False
    referencia = None
    for campo in ("reference_code", "new_code", "old_code"):
        referencia = referencia_crav(_valor(documento, campo))
        if referencia:
            break
    if referencia is None:
        return None, False
    consultado = hasattr(documento, "get") and "referencia_digitarq" in documento
    if consultado:
        return DIGITARQ.format(cota=quote(referencia.rsplit("/", 1)[0], safe="")), True
    return DIGITARQ.format(cota=quote(referencia, safe="")), False


# Rolo dos Códices no DocReader: o rótulo da página é só o códice, sem fólio, e o quadro guardado é
# o do início do volume (build/cotas.py, corpus/resgate_codices.tsv).
ROLO_CODICES = "CODICES"
_FOLIO = re.compile(r"\bfls?\.\s*([0-9][^.]*?(?:v)?)\.?\s*$", re.IGNORECASE)


def _dica_codice(new_code: str | None) -> str:
    m = _FOLIO.search(new_code or "")
    onde = f"o documento está no fl. {m.group(1).strip()}" if m else "procure o fólio do documento"
    return f"O link abre na primeira página do códice; {onde}."


def do_documento(documento) -> dict[str, str | bool | None]:
    """Os links de uma linha de `documentos.parquet`, e o rótulo de cada um.

    Documento de cota reconstruída não tem link nenhum: só o aviso de cota não oficial.
    """
    if cota_reconstruida(documento):
        return {"digitarq": None, "digitarq_rotulo": None, "resgate": None,
                "resgate_rotulo": None, "resgate_direto": False, "resgate_dica": None,
                "aviso_cota": AVISO_COTA_RECONSTRUIDA}
    link, so_caixa = digitarq_do_documento(documento)
    quadro = _valor(documento, "resgate_docreader")
    url_resgate = resgate(quadro)
    direto = bool(quadro) and url_resgate != RESGATE
    codice = direto and quadro.split("#", 1)[0] == ROLO_CODICES
    if codice:
        rotulo = "Códice no Projeto Resgate"
    else:
        rotulo = "Imagem no Projeto Resgate" if direto else "Portal do Projeto Resgate"
    return {
        "digitarq": link,
        "digitarq_rotulo": "Caixa no DigitArq" if so_caixa else "Ficha no DigitArq",
        "resgate": url_resgate,
        "resgate_rotulo": rotulo,
        "resgate_direto": direto,
        "resgate_dica": _dica_codice(_valor(documento, "new_code")) if codice else None,
        "aviso_cota": None,
    }
