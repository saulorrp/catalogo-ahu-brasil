"""O núcleo público: o que saiu do catálogo tem de ficar fora.

O Catálogo AHU-Brasil reúne a busca, os links de acesso, o conversor de cotas e a lista em PDF.
Pessoas, amostras, painel e inferências por modelo de linguagem não fazem parte dele. Estes testes
cobram isso no código, nos artefatos e nas rotas, para que nada volte por engano.
"""
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent

MODULOS_RETIRADOS = ["ahu/pessoas.py", "ahu/amostras.py", "ahu/graficos.py", "ahu/estilo.py",
                     "ahu/lista_eins.py", "ahu/notas_eins.py", "ahu/proveniencia.py",
                     "web/rotas_lista.py", "build/importar_biografias_v2.py", "app.py"]
COLUNAS_RETIRADAS = {"sender_name", "recipient_name", "sender_category", "vector",
                     "typology_impact", "vernacular_score", "justificativa",
                     "scribe_mediation_likely"}
# Palavras que não podem aparecer no código nem nas páginas do núcleo.
PROIBIDAS = re.compile(r"deepseek|perplexity|sonar|srsp|vernacular|\beins\b|zwei|triagem",
                       re.IGNORECASE)


@pytest.mark.parametrize("caminho", MODULOS_RETIRADOS)
def test_modulo_retirado_nao_existe(caminho):
    assert not (RAIZ / caminho).exists()


def _arquivos_do_nucleo():
    for pasta, padroes in (("ahu", ["*.py"]), ("web", ["*.py", "templates/*.html",
                                                        "static/*.js", "static/*.css"]),
                           ("build", ["*.py"])):
        for padrao in padroes:
            yield from (RAIZ / pasta).glob(padrao)


def test_codigo_e_paginas_nao_falam_das_camadas_retiradas():
    achados = []
    for arq in _arquivos_do_nucleo():
        for n, linha in enumerate(arq.read_text(encoding="utf-8").splitlines(), 1):
            if PROIBIDAS.search(linha):
                achados.append(f"{arq.relative_to(RAIZ)}:{n}: {linha.strip()[:80]}")
    assert not achados, "\n".join(achados)




def test_fixture_de_teste_so_tem_campos_do_nucleo():
    import json
    docs = json.loads((RAIZ / "tests" / "fixtures" / "teste_mini_catalogo.json").read_text("utf-8"))
    assert not COLUNAS_RETIRADAS & {k for d in docs for k in d}


@pytest.mark.skipif(not (RAIZ / "app_dados" / "manifest.json").is_file(),
                    reason="app_dados/ ainda não construído")
def test_artefatos_do_app_so_tem_colunas_do_nucleo():
    import pandas as pd
    pasta = RAIZ / "app_dados"
    assert sorted(p.name for p in pasta.glob("*.parquet")) == ["documentos.parquet"]
    colunas = set(pd.read_parquet(pasta / "documentos.parquet").columns)
    assert not colunas & COLUNAS_RETIRADAS
