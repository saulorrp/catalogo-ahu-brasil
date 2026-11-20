"""Testes da construção do app: artefatos, validação do carregamento e coleção nova."""
import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from ahu import dados as mod_dados
from ahu.dados import ErroDados, carregar_sem_cache
from build import construir_app as ca
from build import construir_indice as ci
from build import importar_camadas as ic
from build.importar_base import RAIZ, ErroImportacao, importar
from tests.conftest import documento
from tests.test_construir_indice import Falso

FIXTURE_MINI = RAIZ / "tests" / "fixtures" / "teste_mini_catalogo.json"


# ---------------------------------------------------------------------------
# Um corpus completo de mentira: base, tipologia e embeddings
# ---------------------------------------------------------------------------

def montar_corpus(tmp_path, colecao="t"):
    """Base + tipologia + embeddings (codificador falso)."""
    docs = [documento(1, "CARTA do Conselho Ultramarino sobre a fortaleza."),
            documento(2, "OFÍCIO de D. Manoel de Mello, barão de Laguna.", "OFÍCIO"),
            documento(3, "REQUERIMENTO do conde de Basto e de João Dias.", "REQUERIMENTO")]
    entrada = tmp_path / "catalogo.json"
    entrada.write_text(json.dumps(docs, ensure_ascii=False), encoding="utf-8")
    corpus = tmp_path / "corpus"
    importar(entrada, corpus, colecao, esperado=len(docs))
    ic.importar_camadas(entrada, corpus, colecao)
    ci.construir_indice(corpus, None, "modelo-falso", Falso(), log=lambda *_: None)
    return corpus, entrada


@pytest.fixture()
def corpus(tmp_path):
    return montar_corpus(tmp_path)[0]


@pytest.fixture()
def artefatos(tmp_path, corpus):
    saida = tmp_path / "app_dados"
    ca.construir(corpus, saida)
    return saida


# ---------------------------------------------------------------------------
# Os artefatos
# ---------------------------------------------------------------------------

def test_constroi_os_artefatos_do_nucleo(artefatos):
    esperados = ("manifest.json", "documentos.parquet", "apelidos.json", "embeddings", "lexico")
    assert sorted(p.name for p in artefatos.iterdir()) == sorted(esperados)


def test_documentos_junta_base_e_tipologia(artefatos):
    docs = pd.read_parquet(artefatos / "documentos.parquet")
    assert len(docs) == 3 and docs["doc_uid"].is_unique
    for coluna in ("description", "reference_code", "tipologia", "typology_status"):
        assert coluna in docs.columns, coluna


def test_lexico_tem_os_campos_e_pesos(artefatos):
    from ahu.lexico import Lexico

    docs = pd.read_parquet(artefatos / "documentos.parquet")
    lexico = Lexico(artefatos, docs["doc_uid"].tolist())
    assert lexico.campos == ["tipologia", "descricao", "pasta"]
    assert lexico.pesos == {"tipologia": 1.5, "descricao": 1.0, "pasta": 0.5}
    assert len(lexico) == len(docs)
    pontos = lexico.notas_do_campo("descricao", ["baran", "laguna"])
    assert pontos[1] > 0 and pontos[0] == 0


def test_manifesto_registra_camadas_usadas_e_hashes(artefatos):
    manifesto = json.loads((artefatos / "manifest.json").read_text("utf-8"))
    assert manifesto["corpus"]["camadas"]["tipologia"] == ic.CAMADA_TIPOLOGIA
    assert set(manifesto["corpus"]["camadas"]) == {"tipologia", "embeddings"}
    assert manifesto["contagens"]["documentos"] == 3
    for nome, hash_esperado in manifesto["artefatos"].items():
        obtido = hashlib.sha256((artefatos / nome).read_bytes()).hexdigest()
        assert obtido == hash_esperado, nome


def test_apelidos_levam_o_uid_antigo_ao_atual(tmp_path):
    """A coluna `ahu_sul_doc_uid` da entrada vira o redirecionamento do uid antigo."""
    from build import importar_colecao as icol

    entrada = pd.DataFrame([{
        "doc_uid": "ahu-brasil:0000000001", "folder": "Rio Grande do Sul",
        "description": "CARTA.", "old_code": None, "new_code": "AHU_ACL_CU_019, Cx. 1, D. 1.",
        "reference_code": "PT/AHU/CU/019/0001/00001", "document_id_and_date": "1. 1750",
        "ano_isolado": 1750, "extracted_typology": "CARTA", "ahu_sul_doc_uid": "ahu-sul:abc"}])
    assert icol.apelidos(entrada) == {"ahu-sul:abc": "ahu-brasil:0000000001"}


def test_embeddings_na_ordem_de_documentos(artefatos, corpus):
    docs = pd.read_parquet(artefatos / "documentos.parquet")
    emb = np.concatenate([np.load(p) for p in sorted((artefatos / "embeddings").glob("*.npy"))])
    camada = pd.read_parquet(corpus / "camadas" / "embeddings_modelo_falso_v1" / "indice.parquet")
    vetores = np.load(corpus / "camadas" / "embeddings_modelo_falso_v1" / "embeddings.f16.npy")

    assert emb.shape[0] == len(docs) and emb.dtype == np.float16
    posicao = {u: i for i, u in enumerate(camada["doc_uid"])}
    for i, uid in enumerate(docs["doc_uid"]):
        assert np.array_equal(emb[i], vetores[posicao[uid]])


def test_lexico_em_disco_da_a_mesma_nota_do_rank_bm25(tmp_path):
    """O índice em disco reproduz o `BM25Okapi` com o IDF do Lucene (antigo lexico.pkl)."""
    import math

    from rank_bm25 import BM25Okapi

    from ahu import lexico as mod_lexico

    linhas = [["carta", "rei", "carta"], [], ["oficio", "rei"], ["rei"], ["carta", "governador"]]
    mod_lexico.gravar(tmp_path, {"descricao": linhas}, {"descricao": 1.0}, {"descricao": 1})
    lexico = mod_lexico.Lexico(tmp_path, [str(i) for i in range(len(linhas))])
    bm25 = BM25Okapi([t or [mod_lexico.SENTINELA] for t in linhas])
    df: dict[str, int] = {}
    for doc in bm25.doc_freqs:
        for termo in doc:
            df[termo] = df.get(termo, 0) + 1
    bm25.idf = {t: math.log(1 + (len(linhas) - d + 0.5) / (d + 0.5)) for t, d in df.items()}
    for consulta in (["carta"], ["rei", "carta"], ["rei", "rei"], ["inexistente"]):
        assert np.allclose(lexico.notas_do_campo("descricao", consulta), bm25.get_scores(consulta))
    assert lexico.termos_existentes(["rei", "nada"]) == ["rei"]
    assert lexico.linhas_com_termo("carta").tolist() == [0, 4]
    assert lexico.mascara_de_frase("oficio rei").tolist() == [False, False, True, False, False]


def test_camada_ativa_ambigua_para_a_construcao(tmp_path, corpus):
    arq = corpus / "manifest.json"
    manifesto = json.loads(arq.read_text("utf-8"))
    manifesto["camadas"]["tipologia_v2_experimental"] = {"tipo": "tipologia", "versao": "2",
                                                         "ativa": True, "arquivos": {}}
    arq.write_text(json.dumps(manifesto, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ErroImportacao, match="camadas de tipo 'tipologia' ativas"):
        ca.construir(corpus, tmp_path / "saida")


def test_documento_sem_camada_para_a_construcao(tmp_path, corpus):
    arq = corpus / "camadas" / ic.CAMADA_TIPOLOGIA / "tipologia.parquet"
    pd.read_parquet(arq).iloc[:1].to_parquet(arq, index=False)
    with pytest.raises(ErroImportacao, match="não estão na camada de tipologia"):
        ca.construir(corpus, tmp_path / "saida")


# ---------------------------------------------------------------------------
# A4: o app recusa iniciar com artefato desalinhado ou com hash diferente
# ---------------------------------------------------------------------------

def test_carrega_e_valida_os_artefatos(artefatos):
    d = carregar_sem_cache(artefatos)
    assert len(d.documentos) == 3
    assert d.embeddings.shape[0] == 3
    assert d.colecoes == ["t"]
    assert d.indice_de(d.documentos["doc_uid"].iloc[2]) == 2
    assert d.modelo_embeddings["nome"] == "modelo-falso"


def test_a4_hash_diferente_do_manifesto_recusa(artefatos):
    docs = pd.read_parquet(artefatos / "documentos.parquet")
    docs.loc[0, "description"] = "descrição trocada depois da construção"
    docs.to_parquet(artefatos / "documentos.parquet", index=False)
    with pytest.raises(ErroDados, match="mudou depois da construção"):
        carregar_sem_cache(artefatos)


def test_a4_numero_de_vetores_diferente_recusa(artefatos):
    emb = np.concatenate([np.load(p) for p in sorted((artefatos / "embeddings").glob("*.npy"))])
    np.save(artefatos / "embeddings" / "parte_000.f16.npy", emb[:2])
    _reassinar(artefatos, "embeddings/parte_000.f16.npy")
    with pytest.raises(ErroDados, match="2 vetores e 3 documentos"):
        carregar_sem_cache(artefatos)


def test_a4_ordem_de_uids_diferente_recusa(artefatos):
    docs = pd.read_parquet(artefatos / "documentos.parquet")
    docs.iloc[::-1].to_parquet(artefatos / "documentos.parquet", index=False)
    _reassinar(artefatos, "documentos.parquet")
    with pytest.raises(ErroDados, match="ordem dos uids"):
        carregar_sem_cache(artefatos)


def test_a4_artefato_ausente_recusa(artefatos):
    (artefatos / "apelidos.json").unlink()
    with pytest.raises(ErroDados, match="Artefato ausente"):
        carregar_sem_cache(artefatos)


def test_a4_manifesto_ausente_recusa(artefatos):
    (artefatos / "manifest.json").unlink()
    with pytest.raises(ErroDados, match="não existe"):
        carregar_sem_cache(artefatos)


def test_mensagem_de_erro_diz_o_que_rodar(artefatos):
    (artefatos / "lexico" / "meta.json").unlink()
    with pytest.raises(ErroDados, match="construir_app.py"):
        carregar_sem_cache(artefatos)


def _reassinar(pasta, nome):
    """Atualiza só o hash de um artefato, para testar as verificações seguintes à do hash."""
    arq = pasta / "manifest.json"
    manifesto = json.loads(arq.read_text("utf-8"))
    manifesto["artefatos"][nome] = hashlib.sha256((pasta / nome).read_bytes()).hexdigest()
    arq.write_text(json.dumps(manifesto, ensure_ascii=False), encoding="utf-8")


def test_carregar_usa_cache_por_pasta(artefatos):
    mod_dados._carregar_cacheado.cache_clear()
    primeiro = mod_dados.carregar(artefatos)
    segundo = mod_dados.carregar(artefatos)
    assert primeiro is segundo  # as tabelas e os vetores não são recarregados


# ---------------------------------------------------------------------------
# A11: coleção nova entra sem mudar o código do app
# ---------------------------------------------------------------------------

def test_a11_colecao_teste_mini_entra_sem_mudar_o_codigo(tmp_path):
    corpus, _ = montar_corpus(tmp_path)
    antes = carregar_sem_cache(_construir(corpus, tmp_path / "antes"))
    assert antes.colecoes == ["t"]

    # Só isto: importar a coleção fictícia e reconstruir. Nenhuma linha de código muda.
    assert FIXTURE_MINI.exists(), FIXTURE_MINI
    importar(FIXTURE_MINI, corpus, "teste-mini", esperado=20)
    ic.importar_camadas(FIXTURE_MINI, corpus, "teste-mini")
    ci.construir_indice(corpus, None, "modelo-falso", Falso(), forcar=True, log=lambda *_: None)
    depois = carregar_sem_cache(_construir(corpus, tmp_path / "depois"))

    assert depois.colecoes == ["t", "teste-mini"]
    assert len(depois.documentos) == 23
    assert depois.embeddings.shape[0] == 23
    # As pastas e as tipologias também saem dos dados.
    assert "Ilha Fictícia" in depois.pastas and "Costa Imaginária" in depois.pastas
    assert "BANDO" in depois.tipologias
    # A coleção antiga continua inteira.
    assert int((depois.documentos["colecao"] == "t").sum()) == 3
    assert depois.manifesto["contagens"]["colecoes"] == {"t": 3, "teste-mini": 20}


def test_fixture_mini_tem_20_documentos_ficticios():
    docs = json.loads(FIXTURE_MINI.read_text(encoding="utf-8"))
    assert len(docs) == 20
    assert all(d["reference_code"].startswith("XX/TESTE/") for d in docs)


def _construir(corpus, saida):
    ca.construir(corpus, saida)
    return saida


# ---------------------------------------------------------------------------
# Os artefatos de verdade, se já estiverem construídos
# ---------------------------------------------------------------------------

APP_DADOS = RAIZ / "app_dados"


