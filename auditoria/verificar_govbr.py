"""Confere no lastro do gov.br os documentos do banco que não vêm do ACTD (Códices, Sergipe, parte do
Rio de Janeiro e catálogos temáticos).

Para cada documento, abre a página de origem (`caminho_resgate`) salva no lastro, tira o texto e
verifica se o resumo do banco aparece ali inteiro, sem acento e sem pontuação. Verifica também se
a cota aparece na página.

Uso: python auditoria/verificar_govbr.py PASTA_GOVBR SAIDA.csv
     PASTA_GOVBR tem raw/ (páginas HTML) e, se houver, pdf/ (PDFs ligados nas páginas).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from build.importar_mape import texto_comparavel  # noqa: E402

PR = "https://www.gov.br/bn/pt-br/central-de-conteudos/projeto-resgate"
BASE = PR + "/novos-instrumentos-de-pesquisa"


def candidatos(url: str) -> list[str]:
    u = url.rstrip("/")
    nomes = []
    for raiz in (PR, BASE):
        if u.startswith(raiz + "/"):
            nomes.append(u[len(raiz) + 1 :].replace("/", "__"))
    return nomes


def texto_da_fonte(pasta: Path, url: str, cache: dict) -> str | None:
    if url in cache:
        return cache[url]
    txt = None
    if url.lower().endswith(".pdf"):
        nome = url.rstrip("/").split("/")[-1]
        # a cópia de outubro guardou os dois PDFs do Rio de Janeiro com nomes curtos
        apelidos = {
            "catalogo-documentos-avulsos-rio-de-janeiro-1614-1830.pdf": "rio-de-janeiro-avulsos.pdf",
            "catalogo-documentos-castro-e-almeida-rio-de-janeiro-ahu-1617-1757.pdf": "rio-de-janeiro-castro-e-almeida.pdf",  # noqa: E501
        }
        nomes = [nome] + ([apelidos[nome]] if nome in apelidos else [])
        # a cópia de 21/11 prefixa o nome com seção e pasta: "secao__pasta__nome.pdf"
        achados = [[pasta / "pdf" / n, *pasta.glob(f"**/{n}"), *pasta.glob(f"**/*__{n}")] for n in nomes]
        for p in [q for grupo in achados for q in grupo]:
            if p.exists():
                txt = subprocess.run(["pdftotext", str(p), "-"], capture_output=True).stdout.decode(
                    "utf-8", "replace"
                )
                break
    else:
        for n in candidatos(url):
            p = pasta / "raw" / f"{n}.html"
            if p.exists():
                soup = BeautifulSoup(p.read_text("utf-8", "replace"), "lxml")
                core = soup.select_one("#content-core") or soup
                txt = core.get_text(" ", strip=True)
                break
    cache[url] = texto_comparavel(txt) if txt is not None else None
    return cache[url]


def main(pasta: str, saida: str) -> None:
    pasta = Path(pasta)
    banco = pd.read_parquet(RAIZ / "corpus/colecoes/ahu-brasil/documentos.parquet")
    x = banco[banco.url_actd.isna()].copy()
    cache, linhas = {}, []
    for r in x.itertuples(index=False):
        url = r.caminho_resgate if isinstance(r.caminho_resgate, str) else None
        fonte = texto_da_fonte(pasta, url, cache) if url else None
        desc = texto_comparavel(r.description)
        if fonte is None:
            cls = "fonte_nao_esta_no_lastro"
        elif not desc:
            cls = "banco_sem_resumo"
        elif desc in fonte:
            cls = "resumo_encontrado"
        elif desc[:80] in fonte or desc[-80:] in fonte:
            cls = "resumo_encontrado_em_parte"
        else:
            cls = "resumo_nao_encontrado"
        nums = re.findall(r"\d+", str(r.new_code))
        cota_ok = bool(fonte) and all(n.lstrip("0") in fonte.split() or n in fonte for n in nums[-2:])
        linhas.append(
            {
                "doc_uid": r.doc_uid,
                "folder": r.folder,
                "new_code": r.new_code,
                "classe": cls,
                "cota_na_pagina": cota_ok,
                "cota_suja": len(str(r.new_code)) > 70,
                "caminho_resgate": url,
                "resumo_banco": r.description,
            }
        )
    out = pd.DataFrame(linhas)
    out.to_csv(saida, index=False)
    print(out.classe.value_counts().to_string())
    print(
        "cota suja:",
        int(out.cota_suja.sum()),
        "| cota não achada na página:",
        int((~out.cota_na_pagina).sum()),
    )
    print(out[out.classe == "fonte_nao_esta_no_lastro"].caminho_resgate.value_counts().head(10).to_string())


if __name__ == "__main__":
    main(*sys.argv[1:3])
