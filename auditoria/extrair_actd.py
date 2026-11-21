# ruff: noqa: E741
"""Extração independente dos verbetes dos PDFs do ACTD/IICT (o "lastro").

Não usa o parser da coleta (coleta/scripts/parse_actd.py). O princípio é outro: cada verbete do
catálogo do AHU termina na linha da cota do Resgate (AHU_CU_009, Cx. 2, D. 135). O bloco entre
duas cotas é um verbete. Dentro do bloco:

    135-   [post. 1642], Lisboa                      <- número e data (e local)
           PARECER (minuta) sobre o povoamento ...   <- resumo (começa pela espécie, em maiúsculas)
           Anexo: 1 requerimento.                    <- rodapé: Anexo, Obs., Nota, Nº de inventário,
           AHU-Maranhão, cx. 1, doc. 3                  cota antiga (AHU-...)
           AHU_CU_009, Cx. 2, D. 135                 <- cota (fecha o verbete)

Sergipe (CU-Sergipe.pdf) tem outro formato (fichas "Nº Inventário / Caixa / Documento Nº /
Ementa do documento") e é tratado à parte.

Uso: python auditoria/extrair_actd.py PASTA_DOS_PDFS SAIDA.jsonl
Precisa do pdftotext (poppler). Grava um registro por verbete, com a página do PDF, o texto bruto
do bloco e marcas do que pareceu estranho.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import unicodedata
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from ahu import conversor  # noqa: E402

# a linha da cota às vezes vem com sujeira antes ("CT: AHU_CU_006", "A AHU_CU_008") ou partida
# ("AHU_C, U_015")
COTA = re.compile(
    r"^\s*(?-i:(?:[A-Z]{1,2}:?\s+)?)AHU_\s*(?:ACL_\s*)?C\s*,?\s*U\s*[_,]\s*[\w\- ]+?\s*[,;]?\s*(?:Cx|cx|C\s?x|Cod|C[óo]d)",  # noqa: E501
    re.I,
)
NUMERO = re.compile(r"^\s*(\d{1,5}[A-Z]?)(?:\s*[-–]\s*(.*)|\s*\.(?:\s+(.*))?|\s{2,}(\S.*))?\s*$")
NUMERO_COM_TEXTO = re.compile(r"^\s*(\d{1,5}[A-Z]?)\s*[-–.]\s*(.*)$")
ESPECIE = re.compile(r"^\[?[A-ZÁÉÍÓÚÂÊÔÃÕÇÀÜ][A-ZÁÉÍÓÚÂÊÔÃÕÇÀÜ\-]{2,}")
RODAPE = re.compile(
    r"^(?P<tipo>(?i:anexos?)|(?i:obs)\.?|AHU\s*,|Observa[çc][ãa]o|Nota|N\.?[º°o]\.?\s*de\s+invent[áa]rio|Em\s+anexo|"
    r"AHU\s*[-–]|AHU\s+[A-Z]|Duplicado|DUPLICADO|Ver\s+(?:o\s+)?doc|Vide|Anexa\s+ao|Anexo\s+ao)(?![a-záéíóúâêôãõç])",
)
DATA = re.compile(r"^\s*(\[|\(|\d{3,4}\b|s\.\s*d|ca\.|post\.|ant\.)", re.I)
PAGINA = re.compile(r"^\s*P[ÁA]G\.?\s*[-–]?\s*\d+", re.I)


def dobrar(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def paginas(pdf: Path) -> list[list[str]]:
    texto = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, check=True).stdout
    return [p.splitlines() for p in texto.decode("utf-8", "replace").split("\f")]


def cabecalhos(pags: list[list[str]]) -> set[str]:
    """Títulos correntes: linhas do alto ou do pé da página que se repetem em muitas páginas.

    Só as 6 primeiras e as 3 últimas linhas de cada página contam, para não confundir com
    cabeçalho uma linha de resumo que se repete muito ("ao [secretário de estado da Marinha e")."""
    cont = Counter()
    for p in pags:
        ls = [l.strip() for l in p if l.strip()]
        cont.update({re.sub(r"\d+", "N", l) for l in ls[:6] + ls[-3:]})
    lim = max(5, int(len(pags) * 0.4))
    return {l for l, n in cont.items() if n >= lim and not COTA.match(l)}


def juntar(linhas: list[str]) -> str:
    out = ""
    for l in linhas:
        l = l.strip()
        if not l:
            continue
        if not out:
            out = l
        elif out.endswith("-") and not out.endswith(" -"):
            out += l
        else:
            out += " " + l
    return re.sub(r"\s+", " ", out).strip()


def colchetes_abertos(s: str) -> bool:
    return s.count("[") > s.count("]")


def analisar_bloco(bloco: list[tuple[int, str]], cota_linha: tuple[int, str], primeiro: bool = False) -> dict:
    marcas = []
    linhas = [(p, l) for p, l in bloco if l.strip()]

    # o bloco deve ter um só verbete: vale a última linha de número seguida de data (o que vem
    # antes é introdução, tabela ou título de seção)
    def comeco(i):
        m = NUMERO.match(linhas[i][1])
        if not m:
            return False
        resto = (m.group(2) or m.group(3) or m.group(4) or "").strip()
        alvo = resto or (linhas[i + 1][1].strip() if i + 1 < len(linhas) else "")
        return bool(DATA.match(alvo))

    inis = [i for i in range(len(linhas)) if comeco(i)]
    # no primeiro bloco do PDF vem antes a introdução (tabelas com números): vale o último candidato
    ini = (
        (inis[-1] if primeiro else inis[0])
        if inis
        else next((i for i, (_, l) in enumerate(linhas) if NUMERO.match(l)), None)
    )
    prefixo = [l for _, l in linhas[:ini]] if ini is not None else [l for _, l in linhas]
    if ini is None:
        marcas.append("sem_numero")
        corpo = linhas
        numero, data_partes = None, []
    else:
        m = NUMERO.match(linhas[ini][1])
        numero = m.group(1)
        resto = (m.group(2) or m.group(3) or m.group(4) or "").strip()
        corpo = linhas[ini + 1 :]
        data_partes = [resto] if resto else []
        if not resto and corpo and ESPECIE.match(corpo[0][1].strip()):
            # linha só com um número e o resumo logo depois: nos catálogos sem numeração
            # (Rio de Janeiro, Castro e Almeida) esse número é o ano
            if re.fullmatch(r"1[4-9]\d\d", numero):
                numero, data_partes = None, [numero]
                marcas.append("sem_numero")
        elif not resto and corpo:  # número sozinho na linha: a data vem na seguinte
            data_partes = [corpo[0][1].strip()]
            corpo = corpo[1:]
    # a data pode ocupar mais de uma linha; o resumo começa na espécie documental, em maiúsculas
    k = None
    for i, (_, l) in enumerate(corpo[:4]):
        if RODAPE.match(l.strip()):
            break
        if ESPECIE.match(l.strip()):
            k = i
            break
    if k is None:
        k = 0
        if data_partes and colchetes_abertos(data_partes[0]):
            marcas.append("data_com_colchete_aberto")
    elif k > 0:
        marcas.append("data_em_varias_linhas")
    data_partes += [l.strip() for _, l in corpo[:k]]
    corpo = corpo[k:]
    resumo, rodape, tipo_atual = [], {}, None
    for _, l in corpo:
        s = l.strip()
        m = RODAPE.match(s)
        if m:
            t = dobrar(m.group("tipo")).lower()
            tipo_atual = (
                "cota_antiga"
                if t.startswith("ahu")
                else "remissao"
                if t.startswith(("anexa ao", "anexo ao"))
                else "anexo"
                if t.startswith(("anexo", "em anexo"))
                else "obs"
                if t.startswith(("obs", "observ"))
                else "nota"
                if t.startswith("nota")
                else "inventario"
                if "invent" in t
                else "remissao"
                if t.startswith(("duplicado", "ver", "vide", "anexa ao", "anexo ao"))
                else "cota_antiga"
            )
            rodape.setdefault(tipo_atual, []).append(s)
        elif tipo_atual:
            rodape[tipo_atual].append(s)
        else:
            resumo.append(s)
    texto_resumo = juntar(resumo)
    if not texto_resumo:
        marcas.append("sem_resumo")
    elif not ESPECIE.match(texto_resumo):
        marcas.append("resumo_sem_especie")
    return {
        "numero": numero,
        "data": juntar(data_partes),
        "resumo": texto_resumo,
        **{k: juntar(v) for k, v in rodape.items()},
        "cota_texto": cota_linha[1].strip(),
        "pagina_inicio": linhas[ini][0] if ini is not None else (linhas[0][0] if linhas else cota_linha[0]),
        "pagina_fim": cota_linha[0],
        "prefixo": juntar(prefixo) if prefixo else None,
        "bruto": "\n".join(l.rstrip() for _, l in bloco + [cota_linha]).strip("\n"),
        "marcas": marcas,
    }


def extrair_padrao(pdf: Path) -> list[dict]:
    pags = paginas(pdf)
    cab = cabecalhos(pags)
    regs, bloco = [], []
    for n, pag in enumerate(pags, start=1):
        cheias = [i for i, l in enumerate(pag) if l.strip()]
        bordas = set(cheias[:6] + cheias[-3:])
        for k, l in enumerate(pag):
            s = l.strip()
            recuo = len(l) - len(l.lstrip())
            if (
                not s
                or PAGINA.match(s)
                or (k in bordas and re.sub(r"\d+", "N", s) in cab)
                or (recuo > 60 and not COTA.match(s))
            ):
                bloco.append((n, ""))
                continue
            if COTA.match(s):
                if regs and not any(x.strip() for _, x in bloco):
                    # cota logo depois de outra cota: o mesmo verbete cobre mais de um documento
                    r = dict(
                        regs[-1],
                        cota_texto=s,
                        pagina_fim=n,
                        marcas=regs[-1]["marcas"] + ["mesmo_verbete_que_o_anterior"],
                    )
                    regs.append(r)
                else:
                    regs.append(
                        analisar_bloco(
                            bloco, (n, l), primeiro=not any(r["numero"] for r in regs[-1:]) and len(regs) < 3
                        )
                    )
                bloco = []
            else:
                bloco.append((n, l))
    # o que vem antes do primeiro verbete é introdução e índice: descarta blocos sem número no começo
    while regs and regs[0]["numero"] is None:
        regs.pop(0)
    return regs


SERGIPE_INI = re.compile(
    r"^\s*N[º°o]\s*Invent[áa]rio\s*:?\s*(\d+)\s+Caixa\s*:?\s*(\d+)\s+Documento\s*N[º°o]?\s*:?\s*([\d/\-A-Z ]+)",  # noqa: E501
    re.I,
)


def extrair_sergipe(pdf: Path) -> list[dict]:
    pags = paginas(pdf)
    regs, atual = [], None
    for n, pag in enumerate(pags, start=1):
        for l in pag:
            s = l.strip()
            if not s or PAGINA.match(s):
                continue
            m = SERGIPE_INI.match(s)
            if m:
                atual = {
                    "inventario": m.group(1),
                    "caixa": int(m.group(2)),
                    "documento": m.group(3).strip(),
                    "pagina_inicio": n,
                    "linhas": [],
                    "data_linhas": [],
                }
                regs.append(atual)
                continue
            if atual is None:
                continue
            atual["pagina_fim"] = n
            atual["linhas"].append(s)
    out = []
    for r in regs:
        txt = "\n".join(r["linhas"])
        ano = re.search(r"Ano de Emiss[ãa]o:\s*(.*?)(?=\s{2,}|\s*M[êe]s)|Ano de Emiss[ãa]o:\s*(\S+)", txt)
        mes = re.search(r"M[êe]s de Emiss[ãa]o:\s*(\S*?)(?:\s{2,}|\s*Dia|\s*$)", txt, re.M)
        dia = re.search(r"Dia da Emiss[ãa]o:\s*(\S*)", txt)
        loc = re.search(r"Local da emiss[ãa]o:\s*(.*)", txt)
        em = re.search(r"Ementa do documento:\s*(.*)", txt, re.S)
        resumo = juntar(em.group(1).splitlines()) if em else ""
        doc = r["documento"]
        primeiro = int(re.match(r"\d+", doc).group()) if re.match(r"\d+", doc) else None
        out.append(
            {
                "numero": r["inventario"],
                "data": ", ".join(
                    x
                    for x in [
                        (ano.group(1) or ano.group(2)).strip() if ano else "",
                        mes.group(1).strip() if mes else "",
                        dia.group(1).strip() if dia else "",
                    ]
                    if x
                ),
                "local": loc.group(1).strip() if loc else "",
                "resumo": resumo,
                "cota_texto": f"AHU_CU_022, Cx. {r['caixa']}, D. {doc}",
                "pagina_inicio": r["pagina_inicio"],
                "pagina_fim": r.get("pagina_fim", r["pagina_inicio"]),
                "bruto": "\n".join(r["linhas"]),
                "marcas": [] if resumo else ["sem_resumo"],
                "_doc_primeiro": primeiro,
                "_caixa": r["caixa"],
            }
        )
    return out


def referencia(reg: dict, serie_arquivo: str) -> tuple[str | None, list[str]]:
    """Código de referência a partir da cota impressa, pelo conversor do catálogo."""
    if "_caixa" in reg:  # Sergipe
        if reg["_doc_primeiro"] is None:
            return None, []
        c = conversor.reconhecer(f"AHU_CU_022, Cx. {reg['_caixa']}, D. {reg['_doc_primeiro']}")
        return (conversor.para_referencia(c) if c else None), []
    texto = re.sub(r"^.*?(?=AHU_)", "", reg["cota_texto"])
    texto = re.sub(r"AHU_\s+", "AHU_", texto)
    texto = re.sub(r"_C\s*,\s*U_", "_CU_", texto)
    texto = re.sub(r"CU_\s+", "CU_", texto)
    cotas = conversor.reconhecer_todas(texto)
    refs = [conversor.para_referencia(c) for c in cotas if c.familia == "resgate"]
    refs = [r for r in refs if r]
    return (refs[0] if refs else None), refs[1:]


def main(pasta: str, saida: str) -> None:
    pasta = Path(pasta)
    total = Counter()
    with open(saida, "w", encoding="utf-8") as f:
        for pdf in sorted(pasta.glob("CU-*.pdf")):
            sergipe = pdf.name == "CU-Sergipe.pdf"
            regs = extrair_sergipe(pdf) if sergipe else extrair_padrao(pdf)
            sem_ref = 0
            for i, r in enumerate(regs):
                ref, outras = referencia(r, pdf.name)
                sem_ref += ref is None
                r = {k: v for k, v in r.items() if not k.startswith("_")}
                f.write(
                    json.dumps(
                        {
                            "arquivo": pdf.name,
                            "ordem": i,
                            "reference_code": ref,
                            "outras_referencias": outras,
                            **r,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            marcas = Counter(m for r in regs for m in r["marcas"])
            total[pdf.name] = len(regs)
            print(
                f"{pdf.name}: {len(regs)} verbetes, {sem_ref} sem referência, marcas {dict(marcas)}",
                flush=True,
            )
    print(f"total: {sum(total.values())} verbetes em {len(total)} PDFs")


if __name__ == "__main__":
    main(*sys.argv[1:3])
