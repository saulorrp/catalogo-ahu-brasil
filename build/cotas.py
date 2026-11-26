"""cotas.py — acertos da base do ACTD feitos na construção do app_dados.

Dois acertos de cota, mecânicos e contados no manifesto:

* **`new_code` sem cabeçalho de página.** Na extração de alguns catálogos (Reino, Goiás, Piauí) o
  cabeçalho da página seguinte grudou na cota: `AHU_CU_Reino, Cx. 133, pasta 10. INSTRUMENTO DE
  PESQUISA DOS DOCUMENTOS…`. O cabeçalho sai; a cota fica.
* **`reference_code` refeito pelo conversor atual.** Parte da base trazia a referência montada por
  uma versão antiga do conversor, que lia `AHU_CU_0005-01` como série `000-501` e `AHU_ACL_CU_0013`
  como `001-003`. Quando o `new_code` tem cota reconhecível, a referência sai dele.

Os resumos não são corrigidos: erros que já vêm da fonte (`SãoSão Trindade`, `Barrreto`,
`deTávora`) ficam como estão, e o app os marca com um [sic] (`ficha.marcar_sic`).

Três acertos de dados, achados na auditoria de 12/11/2026 (`scripts/auditar_banco.py`):

* **Pasta com grafia única.** Parte dos verbetes escreve `Montividéu`, parte `Montevidéu` (a grafia da
  cifra): o filtro mostrava duas pastas para a mesma série. Fica a da cifra.
* **Ano que era número de documento.** Quando a data do verbete é só o intervalo de números
  (`1399. 1401`, Bahia, Luísa da Fonseca), o fim do intervalo virou `ano_isolado`. O ano fica vazio.
* **Cota repetida em bloco.** Na extração de um catálogo (Minas Gerais, Cx. 13) a mesma cota
  (`D. 1065`) ficou em 45 verbetes seguidos, cada um com o seu número de catálogo (1066 a 1110).
  Quando um bloco de 3 ou mais verbetes divide a cota, os números de catálogo são seguidos, cada
  um existe no DigitArq naquela caixa e nenhum já é de outro verbete, a cota de cada verbete passa
  a ser a do seu número. O DigitArq é a prova; sem ela, nada muda.
* **Verbetes repetidos não são apagados.** Mesma série, caixa, documento e resumo (sem acento,
  caixa e pontuação) é o mesmo verbete duas vezes: entre coleções (a cota veio torta, `D. .36`, e
  escapou do importador) ou dentro do ahu-brasil. `scripts/listar_duplicatas.py` lista as cópias
  em `corpus/duplicatas.ignore` (fica a primeira, na ordem da base). A
  construção do app marca as cópias na coluna `duplicata_de` e a busca não as devolve, mas elas
  continuam nos dados publicados, por transparência.

* **Cota corrigida com prova.** Quando a fonte imprime uma cota que no AHU/DigitArq é de outro
  documento (erro tipográfico do ACTD, caixa trocada num catálogo temático, cota lida da
  observação), `corpus/cotas_corrigidas.tsv` dá a cota certa e o motivo. A cota impressa vai para
  `cota_na_fonte`, e a ficha mostra as duas. Só entra lá cota conferida no DigitArq.

Estes acertos são da **base do ACTD** (cotas e datas como a extração dos PDFs as deixou). A ligação
de cada cota ao Projeto Resgate e ao DigitArq não mora aqui: é o módulo de compatibilidade,
`compat/`, que serve a qualquer base.
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

import pandas as pd

from ahu.conversor import para_referencia, reconhecer
from compat import IndiceDigitArq

_CABECALHO = re.compile(r"\s*(INSTRUMENTO DE PESQUISA|ARQUIVO HISTÓRICO ULTRAMARINO)\b.*$", re.S)


GRAFIAS_PASTA = {"Montividéu": "Montevidéu"}
_SO_NUMEROS = re.compile(r"^\s*(\d+)\s*[.\-–]\s*(\d+)\s*\.?\s*(\[.*\])?\s*$")
_ANO = re.compile(r"\b(1[5-8]\d\d)\b")


def ano_falso(data, ano, cota):
    """Se a data é só `<início>. <fim>` e o ano é o fim (número de documento, não ano), devolve o
    ano certo: o que a data traz entre colchetes (`[ant. 1660, Novembro, 18]`) ou None. Sem erro,
    devolve False."""
    if ano is None or pd.isna(ano) or not isinstance(data, str):
        return False
    m = _SO_NUMEROS.match(data)
    if not m:
        return False
    ini, fim = int(m.group(1)), int(m.group(2))
    if int(ano) != fim:
        return False
    if not ((cota is not None and cota.documento_fim == fim) or 0 < fim - ini <= 60):
        return False
    ano_colchete = _ANO.search(m.group(3) or "")
    return int(ano_colchete.group(1)) if ano_colchete else None


def _texto_chave(texto) -> str:
    t = unicodedata.normalize("NFKD", str(texto or ""))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def duplicatas(base: pd.DataFrame, cotas_lidas=None) -> pd.Series:
    """Para cada linha que repete um verbete anterior (mesma série, caixa, documento e resumo), o
    doc_uid da primeira ocorrência; None nas demais."""
    if cotas_lidas is None:
        cotas_lidas = [reconhecer(t) if isinstance(t, str) else None for t in base["new_code"]]
    vistos: dict[tuple, str] = {}
    repete = []
    for uid, cota, texto in zip(base["doc_uid"], cotas_lidas, base["description"]):
        chave_texto = _texto_chave(texto)
        if cota is None or cota.serie is None or not chave_texto:
            repete.append(None)
            continue
        chave = (cota.codigo_serie, cota.caixa, cota.documento, cota.documento_fim, chave_texto)
        primeira = vistos.setdefault(chave, uid)
        repete.append(primeira if primeira != uid else None)
    return pd.Series(repete, index=base.index, dtype="object")


_REPETE = re.compile(r"repete\s+(\S+)")


def ler_ignorados(caminho: Path) -> dict[str, str]:
    """doc_uid -> doc_uid mantido, de um arquivo .ignore: o primeiro campo de cada linha é o uid
    ignorado, `# repete <uid>` diz qual fica; `#` sozinho abre comentário."""
    if not caminho.exists():
        return {}
    uids = {}
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        dado, _, nota = linha.partition("#")
        campo = dado.split()
        if campo:
            m = _REPETE.search(nota)
            uids[campo[0]] = m.group(1) if m else ""
    return uids


def ler_corrigidas(caminho: Path) -> pd.DataFrame:
    """A tabela de `corpus/cotas_corrigidas.tsv` (doc_uid, cota, pasta, motivo), sem comentários."""
    colunas = ["doc_uid", "cota", "pasta", "motivo"]
    if not caminho.exists():
        return pd.DataFrame(columns=colunas)
    linhas = [linha.split("\t") for linha in caminho.read_text(encoding="utf-8").splitlines()
              if linha.strip() and not linha.startswith("#")]
    if not linhas or linhas[0] != colunas:
        raise ValueError(f"{caminho}: o cabeçalho deve ser {colunas}.")
    tabela = pd.DataFrame(linhas[1:], columns=colunas)
    if not tabela["doc_uid"].is_unique:
        raise ValueError(f"{caminho}: doc_uid repetido.")
    return tabela


def aplicar_corrigidas(base: pd.DataFrame, corrigidas: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Troca a cota (e, se dada, a pasta) dos documentos de `corrigidas`, guardando a impressa em
    `cota_na_fonte`. Funciona com a base inteira ou só com as colunas que houver."""
    base = base.copy()
    if "cota_na_fonte" not in base.columns:
        base["cota_na_fonte"] = None
    if corrigidas.empty:
        return base, 0
    faltam = set(corrigidas["doc_uid"]) - set(base["doc_uid"])
    if faltam:
        raise ValueError(f"cotas_corrigidas.tsv cita uids que não estão na base: {sorted(faltam)[:3]}")
    por_uid = corrigidas.set_index("doc_uid")
    alvo = base["doc_uid"].isin(por_uid.index)
    uids = base.loc[alvo, "doc_uid"]
    for _, cota in por_uid["cota"].items():
        if not referencia(cota, None):
            raise ValueError(f"cotas_corrigidas.tsv: cota que o conversor não lê: {cota!r}")
    if "new_code" in base.columns:
        base.loc[alvo, "cota_na_fonte"] = base.loc[alvo, "new_code"]
        base.loc[alvo, "new_code"] = uids.map(por_uid["cota"])
    if "reference_code" in base.columns:
        base.loc[alvo, "reference_code"] = uids.map(lambda u: referencia(por_uid.at[u, "cota"], None))
    if "folder" in base.columns:
        pasta = uids.map(por_uid["pasta"])
        com_pasta = pasta.fillna("").str.strip() != ""
        base.loc[pasta[com_pasta].index, "folder"] = pasta[com_pasta]
    return base, int(alvo.sum())


_NUM_CATALOGO = re.compile(r"^\s*(\d+)\.")
_DOC_NA_COTA = re.compile(r"(D\.?\s*)(\d+)(\.?\s*)$")


def curar_blocos(base: pd.DataFrame, cotas_lidas, indice) -> dict:
    """Índice da linha -> (new_code, reference_code) novos, para os blocos de cota repetida que o
    DigitArq confirma (ver o cabeçalho)."""
    if indice is None or "document_id_and_date" not in base.columns:
        return {}
    grupos: dict[tuple, list] = defaultdict(list)
    for i, col, cota in zip(base.index, base.get("colecao", pd.Series("", index=base.index)),
                            cotas_lidas):
        if cota is not None and cota.serie is not None and not cota.documento_fim:
            grupos[(col, cota.codigo_serie, cota.caixa, cota.documento)].append((i, cota))
    usadas = set(base["reference_code"].dropna())
    novo = {}
    for linhas in grupos.values():
        if len(linhas) < 3:
            continue
        nums = []
        for i, _ in linhas:
            m = _NUM_CATALOGO.match(str(base.at[i, "document_id_and_date"] or ""))
            nums.append(int(m.group(1)) if m else None)
        if None in nums or len(set(nums)) != len(nums) or max(nums) - min(nums) != len(nums) - 1:
            continue
        refs = [para_referencia(replace(c, documento=n)) for (_, c), n in zip(linhas, nums)]
        if not all(indice.existe(r) for r in refs) or any(r in usadas for r in refs):
            continue
        for (i, _), n, r in zip(linhas, nums, refs):
            codigo = _DOC_NA_COTA.sub(lambda m, n=n: f"{m.group(1)}{n}{m.group(3)}",
                                      str(base.at[i, "new_code"]).strip())
            novo[i] = (codigo, r)
    return novo


def limpar_new_code(texto):
    if not isinstance(texto, str):
        return texto
    return _CABECALHO.sub("", texto).strip()


def referencia(new_code, reference_code):
    """A referência pelo conversor atual: do `new_code` quando ele traz cota, senão a guardada."""
    for texto in (new_code, reference_code):
        cota = reconhecer(texto) if isinstance(texto, str) else None
        ref = para_referencia(cota) if cota else None
        if ref:
            return ref
    return None


def _mudou(antes: pd.Series, depois: pd.Series) -> int:
    return int((antes.fillna("") != depois.fillna("")).sum())


def ajustar(base: pd.DataFrame, indice: IndiceDigitArq | None) -> tuple[pd.DataFrame, dict]:
    """A base do ACTD com os acertos de cota e de dados, e a contagem de cada um. Os links
    (`referencia_digitarq`, `resgate_docreader`) vêm depois, do módulo `compat`."""
    base = base.copy()
    contagem = {}
    novo = base["new_code"].map(limpar_new_code)
    contagem["new_code_sem_cabecalho"] = _mudou(base["new_code"], novo)
    base["new_code"] = novo
    ref = pd.Series([referencia(n, r) for n, r in zip(base["new_code"], base["reference_code"])],
                    index=base.index, dtype="object")
    antiga = base["reference_code"].where(base["reference_code"].astype(str).str.startswith("PT/"))
    contagem["referencia_refeita"] = int((ref.notna() & (ref != antiga)).sum())
    base["reference_code"] = ref.where(ref.notna(), base["reference_code"])

    lidas = [reconhecer(t) if isinstance(t, str) else None for t in base["new_code"]]
    curadas = curar_blocos(base, lidas, indice)
    contagem["cota_em_bloco_curada"] = len(curadas)
    for i, (codigo, ref) in curadas.items():
        base.at[i, "new_code"], base.at[i, "reference_code"] = codigo, ref
    if curadas:
        lidas = [reconhecer(t) if isinstance(t, str) else None for t in base["new_code"]]
    if "folder" in base.columns:
        pasta = base["folder"].replace(GRAFIAS_PASTA)
        contagem["pasta_grafia_unificada"] = _mudou(base["folder"], pasta)
        base["folder"] = pasta
    if "ano_isolado" in base.columns and "document_id_and_date" in base.columns:
        certo = [ano_falso(d, a, c) for d, a, c in
                 zip(base["document_id_and_date"], base["ano_isolado"], lidas)]
        falso = pd.Series([c is not False for c in certo], index=base.index)
        novo = pd.Series([c if c not in (False, None) else pd.NA for c in certo],
                         index=base.index, dtype="Int64")
        contagem["ano_falso_corrigido"] = int(falso.sum())
        base["ano_isolado"] = base["ano_isolado"].mask(falso, novo).astype("Int64")
    return base, contagem
