"""ficha.py — a ficha de um documento, montada como dado.

A ficha é montada aqui, sem interface, e as páginas só a desenham. O que a ficha tem:
  * título com ano, tipologia e pasta;
  * resumo do AHU, com os termos da busca marcados e os erros da fonte marcados com [sic];
  * as cotas, para copiar, e os links de acesso (DigitArq, Projeto Resgate, ACTD).
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

import pandas as pd

from ahu import links


@dataclass
class Ficha:
    doc_uid: str
    titulo: str
    ano: int | None
    tipologia: str | None
    tipologia_a_revisar: bool
    pasta: str | None
    resumo: str
    resumo_marcado: str
    cotas: dict[str, str] = field(default_factory=dict)
    links: dict[str, str | None] = field(default_factory=dict)
    colecao: str | None = None
    # Tradução inglesa: a do MAPE (camada mape_en_v6), quando o resumo é o mesmo nas duas fontes;
    # senão, a tradução automática do catálogo (camada traducao_en_catalogo_v1).
    resumo_en: str | None = None
    # De quem é a tradução: "mape" ou "catalogo" (None sem tradução).
    resumo_en_fonte: str | None = None
    # O modelo que fez a tradução do catálogo (ex.: gemini-4-hydrogen-low).
    resumo_en_modelo: str | None = None
    # A mesma tradução com os termos da busca marcados (para a página em inglês).
    resumo_en_marcado: str | None = None

    def texto_visivel(self) -> str:
        """Tudo que a ficha mostra, num só texto."""
        partes = [self.titulo, self.resumo, self.resumo_en or "", str(self.ano),
                  self.tipologia or "", self.pasta or ""]
        partes += list(self.cotas.values())
        partes += [str(v) for v in self.links.values() if v]
        return "\n".join(x for x in partes if x)


# ---------------------------------------------------------------------------
# Destaque dos termos
# ---------------------------------------------------------------------------

def marcar_termos(texto: str, termos: list[str], abre: str = "**", fecha: str = "**") -> str:
    """Marca no resumo as palavras que casaram, comparando pela forma normalizada.

    A comparação é feita sobre a forma neutralizada (ahu/texto.py), mas o texto devolvido é o original:
    é assim que 'Mello' aparece marcado quando se buscou 'Melo'.
    """
    from ahu.texto import fonetica, normalizar_busca

    alvos = {fonetica(normalizar_busca(t)) for t in termos if t}
    if not texto or not alvos:
        return texto or ""

    def troca(m: re.Match) -> str:
        palavra = m.group(0)
        return f"{abre}{palavra}{fecha}" if fonetica(normalizar_busca(palavra)) in alvos else palavra

    return re.sub(r"\w+", troca, texto)


# Erros que já vêm da fonte (o texto do Projeto Resgate ou do ACTD, copiado como veio). O app não
# os corrige: marca cada um com um [sic], para que se veja que o erro é da fonte e não do sistema.
ERROS_DA_FONTE = [
    re.compile(r"\bSão ?São\b"),                        # SS. (Santíssima) desdobrado duas vezes
    re.compile(r"\b\w*([a-zà-ú])\1\1\w*"),                 # letra triplicada: Barrreto, possse
    re.compile(r"\b(?:de|da|do|dos|das|ao|aos|par)(?=[A-ZÁÉÍÓÚÂÊÔÃÕ][a-zà-ú])\w+"),  # deTávora
]
SIC = '<span class="sic">[sic]</span>'


def marcar_sic(texto: str) -> str:
    """Põe um [sic] depois de cada erro conhecido da fonte, sem mudar o texto."""
    for padrao in ERROS_DA_FONTE:
        texto = padrao.sub(lambda m: m.group(0) + " " + SIC, texto)
    return texto


# ---------------------------------------------------------------------------
# Montagem
# ---------------------------------------------------------------------------

def _valor(linha, campo):
    """Valor de uma coluna, com None para ausente, NaN e pd.NA."""
    if campo not in linha.index:
        return None
    v = linha[campo]
    return None if v is None or pd.isna(v) else v


def montar(dados, doc_uid: str, termos: list[str] | None = None) -> Ficha:
    """A ficha de um documento. `termos` vêm da `Resposta` da busca, para o destaque."""
    linha = dados.documentos.iloc[dados.indice_de(doc_uid)]
    resumo = str(_valor(linha, "description") or "")
    ano = _valor(linha, "ano_isolado")
    tipologia = _valor(linha, "tipologia")
    pasta = _valor(linha, "folder")
    resumo_en = str(_valor(linha, "resumo_en")) if _valor(linha, "resumo_en") is not None else None
    resumo_en_fonte = (str(_valor(linha, "resumo_en_fonte") or "mape")
                       if resumo_en is not None else None)

    titulo = " · ".join(str(x) for x in (
        int(ano) if ano is not None else "sem data", tipologia or "tipologia a revisar",
        pasta) if x)

    cotas = {etiqueta: str(_valor(linha, campo))
             for campo, etiqueta in (("reference_code", "Código de referência"),
                                     ("new_code", "Código atual"),
                                     ("cota_na_fonte", "Cota impressa na fonte"),
                                     ("old_code", "Código antigo"),
                                     ("document_id_and_date", "Item e data"))
             if _valor(linha, campo) is not None}

    return Ficha(
        doc_uid=doc_uid,
        titulo=titulo,
        ano=int(ano) if ano is not None else None,
        tipologia=str(tipologia) if tipologia is not None else None,
        tipologia_a_revisar=not bool(_valor(linha, "typology_status")),
        pasta=str(pasta) if pasta is not None else None,
        resumo=resumo,
        resumo_marcado=marcar_sic(marcar_termos(html.escape(resumo, quote=False), termos or [])),
        cotas=cotas,
        links=links.do_documento(linha),
        colecao=str(_valor(linha, "colecao")) if _valor(linha, "colecao") is not None else None,
        resumo_en=resumo_en,
        resumo_en_fonte=resumo_en_fonte,
        resumo_en_modelo=(str(_valor(linha, "resumo_en_modelo"))
                          if resumo_en_fonte == "catalogo" and _valor(linha, "resumo_en_modelo")
                          else None),
        resumo_en_marcado=(marcar_termos(html.escape(resumo_en, quote=False), termos or [])
                           if resumo_en else None),
    )
