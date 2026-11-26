"""Tradução inglesa, feita pelo catálogo, dos resumos que o MAPE não traduz.

O catálogo mostra na versão EN a tradução do MAPE (camada `mape_en_v6`). Ficam sem ela 25.528
documentos: os que só existem no catálogo, os sem código de referência (Reino, Códices) e os em
que o resumo do MAPE é outro (semelhança abaixo do limiar). Este script traduz esses resumos com o
Gemini pela linha de comando `agy` (assinatura AI Pro, sem custo), com o comando de PROMPT.md:
glossário fixo de tipologias e cargos, inglês atual, nomes como na fonte.

Subcomandos (rodar na raiz do repositório):
  preparar   monta entrada/fila.jsonl.gz (todos, em lotes) e entrada/piloto.jsonl.gz (amostra)
  rodar      traduz uma fila com um modelo: saida/<modelo>/<lote>.json (retomável)
  verificar  confere as saídas por regra (glossário, nomes, números, colchetes, "galley")
  comparar   página HTML lado a lado de dois modelos para o piloto

Exemplos:
  python coleta/traducao_en/traduzir.py preparar
  python coleta/traducao_en/traduzir.py rodar --fila piloto --modelo gemini-3.8-flash-medium
  python coleta/traducao_en/traduzir.py verificar --modelo gemini-3.8-flash-medium
  python coleta/traducao_en/traduzir.py comparar --modelos gemini-3.8-flash-medium gemini-4-hydrogen-medium
"""
from __future__ import annotations

import argparse
import gzip
import html
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent.parent
ENTRADA = AQUI / "entrada"
SAIDA = AQUI / "saida"
PROMPT = (AQUI / "PROMPT.md").read_text(encoding="utf-8")
TAMANHO_LOTE = 40
MENOR_LOTE = 5
SEMENTE = 20261123

# Tipologia (sem acento, maiúsculas) -> abertura esperada em inglês, conforme o glossário do PROMPT.
GLOSSARIO = {
    "ALVARA": "ROYAL WARRANT", "AVISO": "NOTICE", "ATESTADO": "ATTESTATION", "AUTO": "RECORD",
    "CARTA": "LETTER", "CARTA REGIA": "ROYAL LETTER", "CARTA PATENTE": "LETTERS PATENT",
    "CERTIDAO": "CERTIFICATE", "CONSULTA": "CONSULTATION", "DECRETO": "DECREE",
    "DESPACHO": "RULING", "ESCRITO": "NOTE", "INFORMACAO": "REPORT", "LEMBRETE": "REMINDER",
    "LISTA": "LIST", "MEMORIA": "MEMOIR", "OFICIO": "OFFICIAL LETTER", "ORDEM": "ORDER",
    "PARECER": "OPINION", "PASSAPORTE": "PASSPORT", "PETICAO": "PETITION",
    "PORTARIA": "DIRECTIVE", "PROVISAO": "PROVISION", "RELACAO": "STATEMENT",
    "REPRESENTACAO": "REPRESENTATION", "REQUERIMENTO": "PETITION", "TERMO": "DEED",
    "TRASLADO": "COPY", "BILHETE": "NOTE", "INSTRUCAO": "INSTRUCTIONS",
}
PLURAIS = {"ALVARAS": "ALVARA", "AVISOS": "AVISO", "ATESTADOS": "ATESTADO", "AUTOS": "AUTO",
           "CARTAS": "CARTA", "CARTAS REGIAS": "CARTA REGIA", "CERTIDOES": "CERTIDAO",
           "CONSULTAS": "CONSULTA", "DECRETOS": "DECRETO", "DESPACHOS": "DESPACHO",
           "ESCRITOS": "ESCRITO", "INFORMACOES": "INFORMACAO", "LEMBRETES": "LEMBRETE",
           "LISTAS": "LISTA", "OFICIOS": "OFICIO", "ORDENS": "ORDEM", "PARECERES": "PARECER",
           "PASSAPORTES": "PASSAPORTE", "PORTARIAS": "PORTARIA", "PROVISOES": "PROVISAO",
           "RELACOES": "RELACAO", "REPRESENTACOES": "REPRESENTACAO",
           "REQUERIMENTOS": "REQUERIMENTO", "TERMOS": "TERMO"}
EN_PLURAL = {"ROYAL WARRANT": "ROYAL WARRANTS", "NOTICE": "NOTICES", "ATTESTATION": "ATTESTATIONS",
             "RECORD": "RECORDS", "LETTER": "LETTERS", "ROYAL LETTER": "ROYAL LETTERS",
             "CERTIFICATE": "CERTIFICATES", "CONSULTATION": "CONSULTATIONS", "DECREE": "DECREES",
             "RULING": "RULINGS", "NOTE": "NOTES", "REPORT": "REPORTS", "REMINDER": "REMINDERS",
             "LIST": "LISTS", "OFFICIAL LETTER": "OFFICIAL LETTERS", "ORDER": "ORDERS",
             "OPINION": "OPINIONS", "PASSPORT": "PASSPORTS", "DIRECTIVE": "DIRECTIVES",
             "PROVISION": "PROVISIONS", "STATEMENT": "STATEMENTS",
             "REPRESENTATION": "REPRESENTATIONS", "PETITION": "PETITIONS", "DEED": "DEEDS"}


def agora():
    return time.strftime("%d/%m %H:%M")


def sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


# ---------------------------------------------------------------- preparar

def preparar(args):
    import pandas as pd

    docs = pd.read_parquet(RAIZ / "app_dados" / "documentos.parquet")
    mape = pd.read_parquet(RAIZ / "corpus" / "camadas" / "mape_en_v6" / "mape.parquet")
    divergentes = set(mape.loc[~mape["ligado"], "doc_uid"])
    alvo = docs[docs["resumo_en"].isna() & docs["description"].notna()].copy()
    alvo = alvo[alvo["description"].str.strip() != ""]

    def grupo(linha):
        if linha["doc_uid"] in divergentes:
            return "texto_divergente"
        if pd.isna(linha["reference_code"]) or not str(linha["reference_code"]).strip():
            return "sem_codigo"
        return "so_no_catalogo"

    alvo["grupo"] = alvo.apply(grupo, axis=1)
    print(alvo["grupo"].value_counts().to_string())
    registros = [{"doc_uid": r.doc_uid, "grupo": r.grupo, "pasta": r.folder,
                  "tipologia": r.tipologia_chave if isinstance(r.tipologia_chave, str) else "",
                  "cota": r.new_code if isinstance(r.new_code, str) else "",
                  "texto": " ".join(str(r.description).split())}
                 for r in alvo.itertuples()]

    ENTRADA.mkdir(exist_ok=True)
    grava_fila(ENTRADA / "fila.jsonl.gz", "lote", registros)

    # Piloto: estratificado por grupo, com cotas mínimas para os casos difíceis do glossário.
    rnd = random.Random(SEMENTE)
    escolhidos: dict[str, dict] = {}

    def pega(cond, n):
        pool = [r for r in registros if cond(r) and r["doc_uid"] not in escolhidos]
        for r in rnd.sample(pool, min(n, len(pool))):
            escolhidos[r["doc_uid"]] = r

    pega(lambda r: re.search(r"\bgaleras?\b", r["texto"], re.I), 8)
    pega(lambda r: re.search(r"\b(sumaca|bergantim|charrua|patacho)\b", r["texto"], re.I), 6)
    pega(lambda r: r["tipologia"] == "PARA", 6)
    pega(lambda r: r["tipologia"] in PLURAIS, 12)
    pega(lambda r: len(r["texto"]) > 900, 8)
    pega(lambda r: "[sic]" in r["texto"], 4)
    restante = args.piloto - len(escolhidos)
    total = len(registros)
    for g in ("so_no_catalogo", "sem_codigo", "texto_divergente"):
        n_g = sum(1 for r in registros if r["grupo"] == g)
        pega(lambda r, g=g: r["grupo"] == g, round(restante * n_g / total))
    piloto = sorted(escolhidos.values(), key=lambda r: r["doc_uid"])[: args.piloto]
    grava_fila(ENTRADA / "piloto.jsonl.gz", "piloto", piloto)
    print(f"fila: {len(registros)} verbetes; piloto: {len(piloto)}")


def grava_fila(caminho, prefixo, registros):
    with gzip.open(caminho, "wt", encoding="utf-8") as f:
        for i in range(0, len(registros), TAMANHO_LOTE):
            f.write(json.dumps({"lote": f"{prefixo}_{i // TAMANHO_LOTE:04d}",
                                "docs": registros[i:i + TAMANHO_LOTE]}, ensure_ascii=False) + "\n")


def recortar(args):
    """Uma fila menor com os primeiros N verbetes de outra (ex.: piloto100 a partir do piloto)."""
    docs = [d for lt in le_fila(args.de) for d in lt["docs"]]
    if args.uids:
        quero = Path(args.uids).read_text(encoding="utf-8").split()
        por_uid = {d["doc_uid"]: d for d in docs}
        docs = [por_uid[u] for u in quero if u in por_uid]
    docs = docs[: args.n]
    grava_fila(ENTRADA / f"{args.nome}.jsonl.gz", args.nome, docs)
    print(f"{args.nome}: {len(docs)} verbetes de {args.de}")


def le_fila(nome):
    with gzip.open(ENTRADA / f"{nome}.jsonl.gz", "rt", encoding="utf-8") as f:
        return [json.loads(linha) for linha in f]


# ---------------------------------------------------------------- rodar

class CotaEsgotada(Exception):
    def __init__(self, segundos, texto):
        super().__init__(texto)
        self.segundos = segundos


_trava = threading.Lock()
_pausa = [0.0]


def espera(e):
    with _trava:
        if time.time() >= _pausa[0]:
            _pausa[0] = time.time() + e.segundos + 60
            print(f"{agora()} cota esgotada; pausa até "
                  f"{time.strftime('%d/%m %H:%M', time.localtime(_pausa[0]))}: {e}", flush=True)
    time.sleep(max(0, _pausa[0] - time.time()))


# Sem esta linha, o agy em modo plan tenta usar ferramentas ou escrever um plano e devolve
# resposta vazia (visto no piloto de 23/11/2026, no Hermerico).
SUFIXO = ("\nIMPORTANT: Do not use any tools, do not write files, do not create a plan or ask for "
          "approval. Reply right now with only the JSON array, nothing else.\n")
# O agy roda numa pasta vazia, para não ter arquivos do repositório à mão.
PASTA_VAZIA = Path(tempfile.mkdtemp(prefix="agy_vazio_"))


def texto_do_pedido(docs):
    return (PROMPT.rstrip() + "\n\n" + "\n".join(f"[{i}] {d['texto']}"
                                                    for i, d in enumerate(docs, 1)) + "\n" + SUFIXO)


def chama_agy(pedido, modelo):
    proc = subprocess.run(["agy", "-p", pedido, "--model", modelo, "--mode", "plan",
                           "--output-format", "json", "--print-timeout", "900s"],
                          cwd=PASTA_VAZIA, capture_output=True)
    bruto = proc.stdout.decode("utf-8", errors="replace")
    erro = proc.stderr.decode("utf-8", errors="replace")
    try:
        dados = json.loads(bruto[bruto.index("{"):])
    except ValueError:
        dados = {"response": "", "error": (bruto[:200] + " " + erro[:200]).strip()}
    msg = f"{dados.get('error') or ''} {erro}"
    if "quota" in msg.lower() or "RESOURCE_EXHAUSTED" in msg:
        m = re.search(r"Resets in (?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", msg)
        seg = (int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60
               + int(m.group(3) or 0)) if m else 1800
        raise CotaEsgotada(max(seg, 60), msg.strip()[:200])
    if dados.get("error"):
        raise RuntimeError(str(dados["error"])[:300])
    return dados.get("response") or ""


def le_resposta(texto, docs):
    t = texto.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1].rsplit("```", 1)[0]
    itens = json.loads(t[t.index("["):t.rindex("]") + 1])
    if len(itens) != len(docs) or [i.get("n") for i in itens] != list(range(1, len(docs) + 1)):
        raise ValueError(f"esperava {len(docs)} itens numerados, vieram {len(itens)}")
    saida = []
    for d, i in zip(docs, itens):
        en = " ".join(str(i.get("en") or "").split())
        if not en:
            raise ValueError(f"tradução vazia no item {i.get('n')}")
        saida.append({"doc_uid": d["doc_uid"], "en": en})
    return saida


def processa(docs, args, falhas):
    erro = ""
    for _ in range(2):
        try:
            return le_resposta(chama_agy(texto_do_pedido(docs), args.modelo), docs)
        except CotaEsgotada:
            raise
        except (ValueError, RuntimeError, OSError) as e:
            erro = str(e)[:200]
    if len(docs) > MENOR_LOTE:
        meio = len(docs) // 2
        return processa(docs[:meio], args, falhas) + processa(docs[meio:], args, falhas)
    with _trava, open(falhas, "a", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps({"doc_uid": d["doc_uid"], "erro": erro}, ensure_ascii=False) + "\n")
    return []


def rodar(args):
    pasta = SAIDA / args.modelo
    pasta.mkdir(parents=True, exist_ok=True)
    falhas = pasta / "_falhas.jsonl"
    fila = [lt for lt in le_fila(args.fila) if not (pasta / f"{lt['lote']}.json").exists()]
    total = len(fila)
    print(f"{agora()} {total} lotes por fazer com {args.modelo}, {args.trabalhadores} trabalhadores",
          flush=True)
    feitos = [0]

    def trabalhador():
        while True:
            with _trava:
                if not fila:
                    return
                lote = fila.pop(0)
            inicio = time.time()
            while True:
                try:
                    resultados = processa(lote["docs"], args, falhas)
                    break
                except CotaEsgotada as e:
                    espera(e)
            final = pasta / f"{lote['lote']}.json"
            tmp = final.with_suffix(".tmp")
            tmp.write_text(json.dumps({
                "lote": lote["lote"], "modelo": args.modelo, "rota": "agy",
                "data": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "segundos": round(time.time() - inicio, 1), "docs": resultados},
                ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, final)
            with _trava:
                feitos[0] += 1
                if feitos[0] % 10 == 0 or feitos[0] == total:
                    print(f"{agora()} {feitos[0]}/{total} lotes", flush=True)

    fios = [threading.Thread(target=trabalhador, daemon=True) for _ in range(args.trabalhadores)]
    for t in fios:
        t.start()
    for t in fios:
        t.join()
    print(f"{agora()} fim: {feitos[0]} lotes nesta rodada.", flush=True)


# ---------------------------------------------------------------- verificar

def traducoes(modelo):
    out = {}
    for arq in sorted((SAIDA / modelo).glob("*.json")):
        dados = json.loads(arq.read_text(encoding="utf-8"))
        for d in dados["docs"]:
            out[d["doc_uid"]] = {"en": d["en"], "segundos": dados.get("segundos"),
                                 "lote": dados["lote"]}
    return out


def abertura_esperada(pt: str) -> str | None:
    """A abertura em inglês que o glossário manda para a tipologia que abre o resumo."""
    cabeca = sem_acento(re.match(r"^[^a-z]*", pt).group(0)).upper()
    cabeca = re.split(r"[(,\[]| DO | DA | DE | DOS | DAS ", cabeca + " ")[0].strip()
    plural = cabeca in PLURAIS
    chave = PLURAIS.get(cabeca, cabeca)
    if chave not in GLOSSARIO:
        return None
    en = GLOSSARIO[chave]
    return EN_PLURAL.get(en, en) if plural else en


NUMERO = re.compile(r"\d+")
NOME = re.compile(r"\b[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõçà]{3,}\b")
COMUNS_PT = {"Para", "Sobre", "Estado", "Real", "Reino", "Brasil", "Ultramar", "Marinha", "Rei",
             "Rainha", "Conselho", "Ultramarino", "Fazenda", "Câmara", "Capitania", "Governador",
             "Ordem", "Cristo", "Santo", "Santa", "Senhora", "Nossa", "Junta", "Mesa", "Secretário",
             "Companhia", "Regimento", "Príncipe", "Regente", "Infantaria", "Cavalaria", "Inglaterra",
             "Igreja", "Provedor", "Cidade", "Vila", "Sua", "Majestade", "Alteza", "Estados",
             "Negócios", "Guerra", "Estrangeiros", "Relação", "Corte", "Coroa", "Misericórdia"}


def problemas(pt: str, en: str) -> list[str]:
    p = []
    esperada = abertura_esperada(pt)
    if esperada and not en.upper().lstrip("[(\"' ").startswith(esperada):
        p.append(f"abertura≠{esperada}")
    if re.search(r"\bgalle(y|ys|on)\b", en, re.I) and re.search(r"\bgaler", pt, re.I):
        p.append("galera→galley")
    faltam = sorted(set(NUMERO.findall(pt)) - set(NUMERO.findall(en)))
    if faltam:
        p.append("números:" + ",".join(faltam[:5]))
    if pt.count("[") != en.count("[") or pt.count("(") != en.count("("):
        p.append("colchetes/parênteses")
    nomes = {n for n in NOME.findall(pt) if n not in COMUNS_PT}
    sumidos = sorted(n for n in nomes if n not in en)
    if sumidos:
        p.append("nomes:" + ",".join(sumidos[:5]))
    razao = len(en) / max(len(pt), 1)
    if razao < 0.7 or razao > 1.5:
        p.append(f"tamanho×{razao:.2f}")
    if "*" in en:
        p.append("asterisco")
    return p


def verificar(args):
    import csv

    fila = {d["doc_uid"]: d for lt in le_fila(args.fila) for d in lt["docs"]}
    for modelo in args.modelos:
        tr = traducoes(modelo)
        feitos = [u for u in fila if u in tr]
        contagem: dict[str, int] = {}
        linhas = []
        for u in feitos:
            ps = problemas(fila[u]["texto"], tr[u]["en"])
            for x in ps:
                k = x.split(":")[0].split("≠")[0].split("×")[0]
                contagem[k] = contagem.get(k, 0) + 1
            linhas.append({"doc_uid": u, "grupo": fila[u]["grupo"], "pt": fila[u]["texto"],
                           "en": tr[u]["en"], "problemas": "; ".join(ps)})
        limpos = sum(1 for linha in linhas if not linha["problemas"])
        segs = [v["segundos"] for v in {t["lote"]: t for t in tr.values()}.values()
                if v["segundos"]]
        print(f"{modelo}: {len(feitos)}/{len(fila)} traduzidos; {limpos} sem alerta; "
              f"alertas {dict(sorted(contagem.items()))}; "
              f"{sum(segs) / max(len(segs), 1):.0f} s por lote")
        with open(SAIDA / f"verificacao_{args.fila}_{modelo}.csv", "w", encoding="utf-8-sig",
                  newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(linhas[0]) if linhas else ["doc_uid"],
                               delimiter=";")
            w.writeheader()
            w.writerows(linhas)


# ---------------------------------------------------------------- comparar

def comparar(args):
    """Página única com o resumo do AHU e as traduções dos modelos lado a lado (piloto)."""
    fila = [d for lt in le_fila(args.fila) for d in lt["docs"]]
    trs = {m: traducoes(m) for m in args.modelos}
    dados = []
    for n, d in enumerate(fila, 1):
        item = {"n": n, "doc_uid": d["doc_uid"], "cota": d["cota"], "pasta": d["pasta"],
                "grupo": d["grupo"], "pt": d["texto"]}
        for i, m in enumerate(args.modelos):
            en = trs[m].get(d["doc_uid"], {}).get("en", "")
            item["en" + "AB"[i]] = en
            item["alerta" + "AB"[i]] = "; ".join(problemas(d["texto"], en)) if en else "sem tradução"
        dados.append(item)
    modelo_tpl = (AQUI / "comparar.html").read_text(encoding="utf-8")
    pagina = (modelo_tpl.replace("/*DADOS*/[]", json.dumps(dados, ensure_ascii=False))
              .replace("__MODELO_A__", html.escape(args.modelos[0]))
              .replace("__MODELO_B__", html.escape(args.modelos[1])))
    destino = SAIDA / f"comparar_{args.fila}.html"
    destino.write_text(pagina, encoding="utf-8")
    print(destino)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("preparar")
    p.add_argument("--piloto", type=int, default=200)
    p = sub.add_parser("recortar")
    p.add_argument("--de", default="piloto")
    p.add_argument("--n", type=int, default=100)
    p.add_argument("--nome", default="piloto100")
    p.add_argument("--uids", default="", help="arquivo com os doc_uid escolhidos, um por linha")
    p = sub.add_parser("rodar")
    p.add_argument("--fila", default="piloto")
    p.add_argument("--modelo", required=True)
    p.add_argument("--trabalhadores", type=int, default=2)
    p = sub.add_parser("verificar")
    p.add_argument("--fila", default="piloto")
    p.add_argument("--modelos", nargs="+", required=True)
    p = sub.add_parser("comparar")
    p.add_argument("--fila", default="piloto")
    p.add_argument("--modelos", nargs=2, required=True)
    args = ap.parse_args()
    comandos = {"preparar": preparar, "recortar": recortar, "rodar": rodar,
                "verificar": verificar, "comparar": comparar}
    comandos[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
