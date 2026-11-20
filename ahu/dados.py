"""dados.py — carrega e valida `app_dados/`.

O app chama `carregar()` uma vez. Se qualquer coisa estiver fora do lugar — hash diferente do
manifesto, número de vetores diferente do número de documentos, ordem de `doc_uid` diferente da
registrada — o carregamento **para** com uma mensagem que diz o que reconstruir: um artefato
desalinhado não pode produzir a ficha de outro documento.

O app só lê `app_dados/`. Nada aqui abre `corpus/`.

Uso no app:
    from ahu.dados import carregar
    dados = carregar()          # uma vez por processo; nunca copia as tabelas
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from ahu.lexico import Lexico

RAIZ = Path(__file__).resolve().parent.parent
APP_DADOS = RAIZ / "app_dados"

ARTEFATOS_PARQUET = ("documentos.parquet",)
# Os vetores vêm em partes (`embeddings/parte_000.f16.npy`, ...) e o léxico numa pasta: o
# manifesto lista cada arquivo. Estes são os que não podem faltar.
ARTEFATOS = (*ARTEFATOS_PARQUET, "lexico/meta.json")
PASTA_EMBEDDINGS = "embeddings"
# uid antigo -> uid atual (build/importar_colecao.py). Opcional: sem ele, nenhum redirecionamento.
ARQUIVO_APELIDOS = "apelidos.json"

RECONSTRUIR = "Rode `python build/construir_app.py` para reconstruir os artefatos."


class Vetores:
    """Os vetores dos documentos, em partes lidas por `mmap`: nada vai inteiro para a memória.

    Uma parte só tem menos de 100 MB (o limite de arquivo do GitHub). O cosseno é calculado
    parte por parte, em blocos, para não converter a matriz inteira para float32 de uma vez.
    """

    BLOCO = 20_000

    def __init__(self, partes: list[np.ndarray]):
        self.partes = partes
        dimensao = partes[0].shape[1] if partes and partes[0].ndim == 2 else 0
        self.shape = (sum(p.shape[0] for p in partes), dimensao)
        self.ndim = 2

    def __len__(self) -> int:
        return self.shape[0]

    def produto(self, vetor: np.ndarray) -> np.ndarray:
        saida = np.empty(len(self), dtype=np.float32)
        inicio = 0
        for parte in self.partes:
            for a in range(0, parte.shape[0], self.BLOCO):
                bloco = np.asarray(parte[a:a + self.BLOCO], dtype=np.float32)
                saida[inicio + a: inicio + a + len(bloco)] = bloco @ vetor
            inicio += parte.shape[0]
        return saida


class ErroDados(RuntimeError):
    """Artefatos ausentes, desalinhados ou com hash diferente do manifesto."""


@dataclass(frozen=True, eq=False)
class Dados:
    """Os artefatos de `app_dados/`, já validados. As tabelas não são copiadas."""

    documentos: pd.DataFrame
    embeddings: Vetores
    lexico: Lexico
    manifesto: dict
    pasta: Path
    posicao: dict = field(repr=False, default_factory=dict)
    apelidos: dict = field(repr=False, default_factory=dict)

    @property
    def colecoes(self) -> list[str]:
        """Vêm dos dados, nunca do código."""
        return sorted(self.documentos["colecao"].dropna().unique().tolist())

    @property
    def pastas(self) -> list[str]:
        return sorted(self.documentos["folder"].dropna().unique().tolist())

    @property
    def tipologias(self) -> list[str]:
        return sorted(self.documentos["tipologia"].dropna().unique().tolist())

    @property
    def modelo_embeddings(self) -> dict:
        return self.manifesto.get("modelo_embeddings", {})

    def uid_atual(self, doc_uid: str) -> str:
        """O uid de hoje para um uid de versão antiga do catálogo (ou o próprio uid)."""
        return self.apelidos.get(doc_uid, doc_uid)

    def indice_de(self, doc_uid: str) -> int:
        """Linha de `documentos` (e do vetor) de um doc_uid."""
        try:
            return self.posicao[doc_uid]
        except KeyError:
            raise KeyError(f"doc_uid desconhecido: {doc_uid}") from None


# ---------------------------------------------------------------------------
# Verificações
# ---------------------------------------------------------------------------

def _sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _sha256_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def ler_manifesto(pasta: Path) -> dict:
    arq = pasta / "manifest.json"
    if not arq.exists():
        raise ErroDados(f"{arq} não existe. {RECONSTRUIR}")
    try:
        with open(arq, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ErroDados(f"{arq} está corrompido ({e}). {RECONSTRUIR}") from e


def verificar_hashes(pasta: Path, manifesto: dict) -> None:
    esperados = manifesto.get("artefatos") or {}
    if not esperados:
        raise ErroDados(f"O manifesto não lista os artefatos. {RECONSTRUIR}")
    for nome in ARTEFATOS:
        if nome not in esperados:
            raise ErroDados(f"O manifesto não registra o artefato {nome}. {RECONSTRUIR}")
    for nome, esperado in esperados.items():
        caminho = pasta / nome
        if not caminho.exists():
            raise ErroDados(f"Artefato ausente: {caminho}. {RECONSTRUIR}")
        obtido = _sha256_arquivo(caminho)
        if obtido != esperado:
            raise ErroDados(
                f"{nome} mudou depois da construção: o manifesto espera "
                f"{esperado[:12]}... e o arquivo tem {obtido[:12]}.... {RECONSTRUIR}"
            )


def verificar_alinhamento(dados: dict, manifesto: dict) -> None:
    docs = dados["documentos"]
    emb, lexico = dados["embeddings"], dados["lexico"]

    if docs.empty:
        raise ErroDados(f"documentos.parquet está vazio. {RECONSTRUIR}")
    if not docs["doc_uid"].is_unique:
        raise ErroDados(f"documentos.parquet tem doc_uid repetido. {RECONSTRUIR}")

    if emb.shape[0] != len(docs):
        raise ErroDados(
            f"São {emb.shape[0]} vetores e {len(docs)} documentos. {RECONSTRUIR}"
        )
    dimensao = manifesto.get("modelo_embeddings", {}).get("dimensao")
    if dimensao and emb.ndim == 2 and emb.shape[1] != dimensao:
        raise ErroDados(
            f"Os vetores têm {emb.shape[1]} dimensões e o manifesto diz {dimensao}. {RECONSTRUIR}"
        )

    uids = docs["doc_uid"].astype(str).tolist()
    esperado = manifesto.get("doc_uids_sha256")
    if esperado and _sha256_texto("\n".join(uids)) != esperado:
        raise ErroDados(
            f"A ordem dos uids de documentos.parquet não é a registrada no manifesto. {RECONSTRUIR}"
        )

    if len(lexico) != len(uids):
        raise ErroDados(f"O léxico tem {len(lexico)} linhas e são {len(uids)} documentos. "
                        f"{RECONSTRUIR}")



# ---------------------------------------------------------------------------
# Carregamento
# ---------------------------------------------------------------------------

def carregar_sem_cache(pasta: Path | str = APP_DADOS) -> Dados:
    pasta = Path(pasta)
    if not pasta.is_dir():
        raise ErroDados(f"A pasta de artefatos não existe: {pasta}. {RECONSTRUIR}")
    manifesto = ler_manifesto(pasta)
    verificar_hashes(pasta, manifesto)

    dados = {nome.split(".")[0]: pd.read_parquet(pasta / nome) for nome in ARTEFATOS_PARQUET}
    partes = sorted(n for n in manifesto["artefatos"] if n.startswith(f"{PASTA_EMBEDDINGS}/"))
    dados["embeddings"] = Vetores([np.load(pasta / n, mmap_mode="r") for n in partes])
    dados["lexico"] = Lexico(pasta, dados["documentos"]["doc_uid"].astype(str).tolist())

    verificar_alinhamento(dados, manifesto)
    apelidos = {}
    if (pasta / ARQUIVO_APELIDOS).exists():
        with open(pasta / ARQUIVO_APELIDOS, encoding="utf-8") as f:
            apelidos = json.load(f)

    return Dados(
        documentos=dados["documentos"], embeddings=dados["embeddings"], lexico=dados["lexico"],
        manifesto=manifesto, pasta=pasta,
        posicao={uid: i for i, uid in enumerate(dados["documentos"]["doc_uid"].astype(str))},
        apelidos=apelidos,
    )


@lru_cache(maxsize=4)
def _carregar_cacheado(pasta: str) -> Dados:
    return carregar_sem_cache(Path(pasta))


def carregar(pasta: Path | str = APP_DADOS) -> Dados:
    """Carrega os artefatos uma vez por processo."""
    return _carregar_cacheado(str(pasta))
