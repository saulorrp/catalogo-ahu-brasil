"""compat — o módulo de compatibilidade: de uma cota do AHU ao documento no Resgate e no DigitArq.

É a parte do catálogo que este projeto produziu, e não a fonte dos resumos. Funciona com qualquer
base que traga o código de referência do AHU (`PT/AHU/CU/<série>/<caixa>/<documento>`): a base do
ACTD, que o site usa, ou a base aberta do MAPE, para quem quiser reproduzir o catálogo
(`scripts/montar_base_mape.py`). As tabelas ficam em `compat/dados/` e são descritas em
`compat/LEIA-ME.md`; a licença do módulo é CC BY 4.0.

As tabelas:

* **`resgate_docreader.tsv.gz`**: código de referência → rolo e quadro do visualizador de imagens do
  Projeto Resgate (DocReader da Biblioteca Nacional), como `004_AL#1`. Vem dos links das páginas de
  verbetes do gov.br e da varredura do próprio DocReader (`coleta/docreader/`).
* **`digitarq_referencias.tsv.gz`**: os registros do DigitArq, listados caixa a caixa
  (`coleta/scripts/varrer_digitarq.py`). O DigitArq descreve muitos documentos em intervalo
  (`…/017-001/0016/03265.03267`), e o intervalo dele nem sempre começa onde começa o da base; cada
  documento recebe o registro que tem o seu número.
* **`resgate_codices.tsv`**: o primeiro quadro de cada Códice no rolo `CODICES` do DocReader.
* **`concordancia_cota_antiga.tsv.gz`**: código de referência → cota antiga (a numeração anterior
  do AHU, `AHU-Alagoas, cx. 5, doc. 75`). São identificadores, sem texto de resumo. Com ela, o
  conversor de cotas funciona também numa base que não traz a cota antiga.

**Intervalos.** O MAPE copia o DigitArq e descreve parte dos documentos em intervalo
(`…/0001/00009.00019`, um documento principal e os anexos). O quadro do Resgate é o do primeiro
número do intervalo que tiver quadro, e a cota antiga é a do primeiro número. O link do DigitArq é
o próprio registro. Intervalos de mais de `MAX_INTERVALO` números, invertidos ou com letra
(`01335.A`) só ganham o que o primeiro número der.

Uso:
    from compat import Tabelas, ligar
    base, contagem = ligar(base, Tabelas.ler())
"""
from __future__ import annotations

import gzip
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

PASTA = Path(__file__).resolve().parent / "dados"
VERSAO = "1"
MAX_INTERVALO = 50

_REGISTRO = re.compile(r"^(PT/AHU/CU/[\d-]+)/(\d{4})/(\d+)(?:\.(\d+))?$")
# Um código de referência com intervalo e o que vem depois (`.A`, `.00019`, `.A.01998.B`).
_INTERVALO = re.compile(r"^(PT/AHU/CU/[\d-]+/\d{4}/)(\d+)(?:\.(\d+))?(\.\S*)?$")
RE_CODICE = re.compile(r"^\s*AHU_ACL_CU,\s*C[óo]d\.\s*(\d+)\b", re.IGNORECASE)


class IndiceDigitArq:
    """Os registros do DigitArq por série: (início, fim, caixa, referência)."""

    def __init__(self, registros):
        self.por_serie = defaultdict(list)
        for ref in registros:
            m = _REGISTRO.match(ref)
            if m:
                serie, caixa, ini, fim = m.groups()
                self.por_serie[serie].append((int(ini), int(fim or ini), caixa, ref))

    @classmethod
    def ler(cls, caminho: Path) -> "IndiceDigitArq | None":
        if not caminho.exists():
            return None
        with gzip.open(caminho, "rt", encoding="utf-8") as f:
            return cls(linha.split("\t")[0].strip() for linha in f if linha.startswith("PT/"))

    def existe(self, ref: str) -> bool:
        m = _REGISTRO.match(ref or "")
        if not m:
            return False
        serie, caixa, numero = m.group(1), m.group(2), int(m.group(3))
        return any(ini == numero and fim == numero and cx == caixa
                   for ini, fim, cx, _ in self.por_serie.get(serie, ()))

    def achar(self, ref: str | None) -> str | None:
        """O registro com o número do documento: mesmo início antes de intervalo que o contém, e
        a mesma caixa antes de outra caixa da série (há caixas trocadas entre catálogo e DigitArq)."""
        m = _REGISTRO.match(ref or "")
        if not m:
            return None
        serie, caixa, numero = m.group(1), m.group(2), int(m.group(3))
        candidatos = [r for r in self.por_serie.get(serie, ()) if r[0] <= numero <= r[1]]
        if not candidatos:
            return None
        candidatos.sort(key=lambda r: (r[0] != numero, r[2] != caixa, r[1] - r[0]))
        return candidatos[0][3]


def ler_docreader(caminho: Path) -> dict[str, str] | None:
    """Referência CRAV -> `rolo#quadro` do DocReader do Resgate. None quando o índice não existe."""
    if not caminho.exists():
        return None
    with gzip.open(caminho, "rt", encoding="utf-8") as f:
        linhas = (linha.rstrip("\n").split("\t") for linha in f if linha.startswith("PT/"))
        return {ref: f"{bib}#{pagfis}" for ref, bib, pagfis in linhas}


def ler_codices(caminho: Path) -> dict[str, str] | None:
    """Número do códice -> `rolo#quadro` do início do códice no DocReader. None sem o índice."""
    if not caminho.exists():
        return None
    tabela = pd.read_csv(caminho, sep="\t", dtype=str)
    return {c: f"{b}#{p}" for c, b, p in zip(tabela["codice"], tabela["bib"], tabela["pagfis_inicio"])}


def ler_concordancia(caminho: Path) -> dict[str, str] | None:
    """Referência CRAV -> cota antiga. None quando a tabela não existe."""
    if not caminho.exists():
        return None
    with gzip.open(caminho, "rt", encoding="utf-8") as f:
        linhas = (linha.rstrip("\n").split("\t") for linha in f if linha.startswith("PT/"))
        return {ref: antiga for ref, antiga in linhas}


def quadro_do_codice(new_code, codices: dict[str, str]) -> str | None:
    """O quadro do início do códice para uma cota `AHU_ACL_CU, Cód. N, fl. ...`, ou None."""
    m = RE_CODICE.match(new_code) if isinstance(new_code, str) else None
    return codices.get(m.group(1)) if m else None


def numeros(ref) -> list[str]:
    """As referências de cada número de um código, na ordem: o próprio código primeiro, depois o
    primeiro número e, num intervalo válido, os outros (até MAX_INTERVALO)."""
    if not isinstance(ref, str):
        return []
    m = _INTERVALO.match(ref.strip())
    if not m or (m.group(3) is None and m.group(4) is None):
        return [ref]
    prefixo, ini, fim = m.group(1), int(m.group(2)), m.group(3)
    saida = [ref, f"{prefixo}{ini:05d}"]
    if fim is not None and m.group(4) is None and 0 < int(fim) - ini <= MAX_INTERVALO:
        saida += [f"{prefixo}{n:05d}" for n in range(ini + 1, int(fim) + 1)]
    return saida


def procurar(ref, tabela: dict[str, str]) -> str | None:
    """O valor da tabela para o código, ou para o primeiro número dele que a tabela tiver."""
    for r in numeros(ref):
        valor = tabela.get(r)
        if valor is not None:
            return valor
    return None


@dataclass
class Tabelas:
    digitarq: IndiceDigitArq | None = None
    docreader: dict[str, str] | None = None
    codices: dict[str, str] | None = None
    concordancia: dict[str, str] | None = None

    @classmethod
    def ler(cls, pasta: Path | str = PASTA) -> "Tabelas":
        pasta = Path(pasta)
        return cls(
            digitarq=IndiceDigitArq.ler(pasta / "digitarq_referencias.tsv.gz"),
            docreader=ler_docreader(pasta / "resgate_docreader.tsv.gz"),
            codices=ler_codices(pasta / "resgate_codices.tsv"),
            concordancia=ler_concordancia(pasta / "concordancia_cota_antiga.tsv.gz"),
        )


def ligar(base: pd.DataFrame, tabelas: Tabelas, cota_antiga: bool = False) -> tuple[pd.DataFrame, dict]:
    """A base com `referencia_digitarq` e `resgate_docreader`, e a contagem de cada ligação.

    `cota_antiga=True` preenche o `old_code` vazio pela tabela de concordância (para bases que não
    trazem a cota antiga, como a do MAPE). A base do ACTD já traz a sua e não usa a tabela.
    """
    base = base.copy()
    contagem = {}
    indice = tabelas.digitarq
    if indice is not None:
        base["referencia_digitarq"] = [indice.achar(r) if isinstance(r, str) else None
                                       for r in base["reference_code"]]
        com_ref = base["reference_code"].astype(str).str.startswith("PT/")
        contagem["digitarq_com_registro"] = int(base["referencia_digitarq"].notna().sum())
        contagem["digitarq_sem_registro"] = int((com_ref & base["referencia_digitarq"].isna()).sum())
        contagem["digitarq_registro_diferente"] = int(
            (base["referencia_digitarq"].notna()
             & (base["referencia_digitarq"] != base["reference_code"])).sum())
    if tabelas.docreader is not None:
        base["resgate_docreader"] = [procurar(r, tabelas.docreader) for r in base["reference_code"]]
    if tabelas.codices is not None:
        if "resgate_docreader" not in base.columns:
            base["resgate_docreader"] = None
        do_codice = [None if isinstance(q, str) else quadro_do_codice(n, tabelas.codices)
                     for q, n in zip(base["resgate_docreader"], base["new_code"])]
        contagem["resgate_codice_inicio"] = sum(q is not None for q in do_codice)
        base["resgate_docreader"] = [q if isinstance(q, str) else c
                                     for q, c in zip(base["resgate_docreader"], do_codice)]
    if tabelas.docreader is not None or tabelas.codices is not None:
        contagem["resgate_com_quadro"] = int(base["resgate_docreader"].notna().sum())
    if cota_antiga and tabelas.concordancia is not None:
        if "old_code" not in base.columns:
            base["old_code"] = None
        vazio = base["old_code"].isna()
        base.loc[vazio, "old_code"] = [procurar(r, tabelas.concordancia)
                                       for r in base.loc[vazio, "reference_code"]]
        contagem["cota_antiga_da_concordancia"] = int(base.loc[vazio, "old_code"].notna().sum())
    return base, contagem
