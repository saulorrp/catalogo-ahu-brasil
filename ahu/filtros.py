"""filtros.py — os filtros da busca, como máscara sobre `documentos.parquet`.

Dois lados:

* **`Filtros`**: o estado dos controles, que o `ahu/consulta.py` serializa para a URL e para o
  bloco de proveniência. `mascara(dados)` devolve o vetor booleano que a busca recebe.
* **`opcoes(dados)`**: as listas que a interface oferece. Saem **dos dados** — coleções, pastas e
  tipologias. Nenhuma delas está escrita no código, e por isso uma coleção nova aparece nos
  filtros sem mexer no app.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Iterable

import numpy as np
import pandas as pd


@dataclass
class Filtros:
    """O estado dos controles. Vazio = filtro desligado."""

    colecoes: list[str] = field(default_factory=list)
    ano_de: int | None = None
    ano_ate: int | None = None
    sem_data: bool = True          # "incluir documentos sem data"
    pastas: list[str] = field(default_factory=list)
    tipologias: list[str] = field(default_factory=list)

    # -----------------------------------------------------------------
    def vazio(self) -> bool:
        padrao = Filtros()
        return all(getattr(self, f.name) == getattr(padrao, f.name) for f in fields(self))

    def ativos(self) -> dict:
        """Só o que está diferente do padrão — é o que vai para a URL e para a proveniência."""
        padrao = Filtros()
        return {f.name: getattr(self, f.name) for f in fields(self)
                if getattr(self, f.name) != getattr(padrao, f.name)}

    # -----------------------------------------------------------------
    def mascara(self, dados) -> np.ndarray | None:
        """Vetor booleano sobre `documentos.parquet`, ou None se nada estiver filtrado."""
        if self.vazio():
            return None
        docs = dados.documentos
        m = np.ones(len(docs), dtype=bool)

        m &= _em(docs["colecao"], self.colecoes)
        m &= _em(docs.get("folder"), self.pastas)
        m &= _em(docs.get("tipologia"), self.tipologias)

        if self.ano_de is not None or self.ano_ate is not None or not self.sem_data:
            anos = pd.to_numeric(docs["ano_isolado"], errors="coerce")
            dentro = np.ones(len(docs), dtype=bool)
            if self.ano_de is not None:
                dentro &= (anos >= self.ano_de).fillna(False).to_numpy()
            if self.ano_ate is not None:
                dentro &= (anos <= self.ano_ate).fillna(False).to_numpy()
            sem_ano = anos.isna().to_numpy()
            # "incluir documentos sem data" salva quem não tem ano de ser cortado pelo período.
            m &= (dentro & ~sem_ano) | (sem_ano & self.sem_data)
        return m


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------

def _em(coluna, valores: Iterable[str]) -> np.ndarray | bool:
    valores = [v for v in (valores or []) if v]
    if coluna is None or not valores:
        return True
    return coluna.isin(valores).to_numpy()


# ---------------------------------------------------------------------------
# Opções para a interface — sempre dos dados
# ---------------------------------------------------------------------------

def _contagem(coluna) -> list[tuple[str, int]]:
    if coluna is None:
        return []
    return [(str(k), int(v)) for k, v in coluna.dropna().value_counts().items()]


def opcoes(dados) -> dict:
    """O que cada controle oferece, com contagem na tipologia."""
    docs = dados.documentos
    anos = pd.to_numeric(docs["ano_isolado"], errors="coerce")
    return {
        "colecoes": sorted(docs["colecao"].dropna().unique().tolist()),
        # O controle de coleção fica oculto enquanto houver só uma.
        "mostrar_colecao": int(docs["colecao"].nunique()) > 1,
        "ano_minimo": None if anos.dropna().empty else int(anos.min()),
        "ano_maximo": None if anos.dropna().empty else int(anos.max()),
        "documentos_sem_data": int(anos.isna().sum()),
        "pastas": sorted(docs["folder"].dropna().unique().tolist()),
        # Tipologia com contagem, por frequência.
        "tipologias": _contagem(docs.get("tipologia")),
    }
