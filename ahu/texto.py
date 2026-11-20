"""texto.py — normalização de texto para a busca, igual no corpus e na consulta.

Mudar qualquer regra daqui muda os tokens do léxico BM25: depois de mudar, reconstrua
`app_dados/` com `build/construir_app.py`.
"""
from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# Normalização de busca, usada igualmente no corpus e na consulta
# ---------------------------------------------------------------------------

# Lista curta e revisada. Fora dela, nada é removido.
STOPWORDS = frozenset({"de", "do", "da", "dos", "das", "a", "o", "as", "os", "e", "em", "para",
                       "ao", "aos", "que", "com", "por", "na", "no"})

_RE_DOBRADA = re.compile(r"(.)\1")
_RE_SEM_ACENTO = re.compile(r"[^a-z0-9\s]+")


def fonetica(palavra: str) -> str:
    """Neutraliza grafia antiga: 'Paes'~'Pais', 'Jozé'~'José', 'Mello'~'Melo', 'Xássim'~'Chassim'.

    Todo `z` vira `s` (não só no fim), consoantes dobradas viram simples e há também `oe -> oi`.
    """
    t = _RE_DOBRADA.sub(r"\1", palavra)
    for antiga, nova in (("ae", "ai"), ("oe", "oi"), ("ch", "x"), ("z", "s"), ("y", "i"),
                         ("th", "t"), ("ph", "f")):
        t = t.replace(antiga, nova)
    return t


def normalizar_busca(texto: str) -> str:
    """NFKD sem acentos, minúsculas, pontuação virando espaço."""
    if not texto:
        return ""
    t = unicodedata.normalize("NFKD", str(texto))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", _RE_SEM_ACENTO.sub(" ", t)).strip()


def tokenizar(texto: str, stopwords: bool = True, foneticamente: bool = True) -> list[str]:
    """Tokens de busca de um campo ou de uma consulta.

    `stopwords=False` mantém a lista curta de palavras vazias (útil para frase entre aspas);
    `foneticamente=False` mantém a grafia como está.
    """
    tokens = []
    for palavra in normalizar_busca(texto).split():
        if stopwords and palavra in STOPWORDS:
            continue
        tokens.append(fonetica(palavra) if foneticamente else palavra)
    return tokens
