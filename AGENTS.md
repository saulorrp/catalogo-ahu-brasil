# AGENTS.md — Catálogo AHU-Brasil

Guia único para qualquer agente de IA (Claude, Gemini, Codex etc.). `CLAUDE.md` e `GEMINI.md` só
apontam para este arquivo.

## Propósito

Busca no catálogo do Arquivo Histórico Ultramarino (AHU) para o Brasil colonial. O catálogo leva o
pesquisador de uma pergunta a um conjunto de cotas que ele possa justificar, citar e pedir no
arquivo. O núcleo tem quatro partes, e só elas:

1. **Busca** (rota de cotas, BM25 por campos, e5-small, reranker no servidor; filtros por período,
   pasta e tipologia).
2. **Links de acesso** (DigitArq, DocReader do Projeto Resgate, página do ACTD).
3. **Conversor de cotas** (referência ↔ Resgate ↔ cota antiga).
4. **Lista em PDF** para levar ao arquivo.

Qualquer coisa fora disso (inferências por modelo de linguagem, pessoas, amostras, painéis) não
entra neste repositório. `tests/test_nucleo_publico.py` cobra isso.

## Regras

1. **O app só lê `app_dados/`.** Nunca lê `corpus/` nem as camadas brutas.
2. **Os resumos do AHU nunca são reescritos.** Erros da fonte ficam como estão e ganham `[sic]` só
   na exibição; correções vão para colunas separadas. Ver [`LICENSE-DATA.md`](LICENSE-DATA.md).
3. **Nada pago em funcionamento.** Chamadas a modelos pagos, se houver, só na construção dos dados.
4. **`doc_uid` é interno.** Não entra em rótulo, tabela nem PDF: o pesquisador vê cota, ano e
   resumo. Uids antigos continuam abrindo pelo `app_dados/apelidos.json` (redirecionamento 301).
5. **Pastas, coleções e tipologias vêm dos dados, nunca do código.**
6. **Nenhum segredo no código.** Chaves ficam no `.env` local e nunca são versionadas.
7. **Dependências fixadas com versão, em número mínimo.** O `torch` é o só-CPU.
8. **Links salvos não quebram.** Mudar uma chave curta da URL exige subir `VERSAO_URL` em
   `ahu/consulta.py`; parâmetros retirados são descartados em silêncio (`CHAVES_RETIRADAS`).

## Estrutura

```
ahu/          lógica: dados, busca, consulta e filtros, ficha, links, conversor, lista em PDF
ahu/fontes/   Noto Serif embutida no PDF (SIL OFL)
web/          interface FastAPI + Jinja2 + HTMX (htmx vendorizado, sem build de JS)
build/        construção: importar_colecao, importar_camadas, construir_indice, construir_app,
              construir_estatico, cotas
coleta/       scripts da coleta (ACTD, Resgate, OCR), publicados como rodaram, e relatórios de QC
corpus/       coleção + camadas (tipologia, embeddings) e o manifest.json
app_dados/    artefatos que o app lê
avaliacao/    consultas de ouro, julgamentos, métricas (nDCG@10, Recall@20, MRR)
deploy/       Dockerfile auxiliar, compose e guia do servidor
scripts/      gate.py, auditar_banco.py, medir_memoria.py, reconstruir.sh
tests/        pytest
```

## Comandos

```
python scripts/gate.py                          # ruff + pytest; PASS antes de cada commit
python -m uvicorn web.main:app --port 8000      # o catálogo em http://localhost:8000

python build/importar_colecao.py --entrada documentos.parquet --colecao ahu-brasil
python build/importar_camadas.py --entrada documentos.parquet --colecao ahu-brasil  # tipologia
python build/construir_indice.py --modelo intfloat/multilingual-e5-small
python build/construir_app.py                   # artefatos de app_dados/
python build/construir_estatico.py              # índice estático (model2vec) para a versão leve
python scripts/medir_memoria.py                 # RSS e tempo da carga fria
```

A ordem acima é a ordem de construção. O `construir_indice.py` reaproveita o vetor de todo
documento cujo texto não mudou (mesmo uid e mesmo sha1) e só calcula os outros; o arquivo de
vetores da camada em `corpus/camadas/embeddings_*` não vai para o Git (é recriado pelo build e
copiado para `app_dados/embeddings/`).

A busca está em `ahu/busca.py`: `buscar(dados, texto, modo, rigor, encoder)`. Sem `encoder` ela é
só léxica (útil em teste).

## Variáveis de ambiente

`AHU_ROOT_PATH` (subcaminho, ex. `/ahu`), `AHU_RERANKER=1`, `AHU_RERANKER_TOPO` (30),
`AHU_RERANKER_TOKENS` (192), `AHU_SEM_AQUECIMENTO=1`, `AHU_ONNX_CACHE`, `AHU_LOG_DIR`.
Saúde: `/saude` (`{"status": "ok", "documentos": …, "versao_artefatos": …, "commit": …}`).

## Convenção de trabalho

- Um assunto por commit, com testes passando (`gate.py` = PASS).
- Lógica de negócio em `ahu/`; `web/` só monta páginas.
- Números citados em documentação saem de um comando que os reproduz.
