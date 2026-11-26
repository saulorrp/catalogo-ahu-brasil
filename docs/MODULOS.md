# As partes do catálogo

*English summary at the end.*

O Catálogo AHU-Brasil tem três partes. O núcleo e o módulo de compatibilidade estão neste
repositório. A base fica fora dele: cada pessoa monta a sua.

```
             ┌─────────────────────────────────────────────┐
             │ NÚCLEO (ahu/, web/)                         │
             │ interface · busca por palavras e por        │
             │ sentido · conversor de cotas · lista em PDF │
             └───────────────▲─────────────────────────────┘
                             │ lê só app_dados/
             ┌───────────────┴─────────────────────────────┐
             │ CONSTRUÇÃO (build/construir_app.py)         │
             │ base no formato comum + compatibilidade     │
             └──────▲───────────────────────────▲──────────┘
                    │                           │
   ┌────────────────┴──────────┐   ┌────────────┴──────────────────┐
   │ BASE (corpus/, local)     │   │ COMPATIBILIDADE (compat/)     │
   │  ACTD → o site            │   │ cota → imagem no Resgate      │
   │  MAPE → reprodução aberta │   │ cota → registro do DigitArq   │
   │ no "formato comum"        │   │ cota → cota antiga            │
   └───────────────────────────┘   └───────────────────────────────┘
```

## O núcleo

`ahu/` (busca, conversor de cotas, ficha, lista em PDF) e `web/` (o site, em FastAPI). O núcleo
não sabe de onde veio a base: lê só a pasta `app_dados/`, que a construção monta. O que muda de
uma base para outra (o crédito no rodapé e na página "Sobre") vem do campo `base` do
`app_dados/manifest.json`.

## O módulo de compatibilidade

`compat/` liga cada cota ao lugar onde o documento pode ser visto. É a produção própria deste
projeto e não traz nenhum resumo. Por isso tem licença aberta (CC BY 4.0) e pode ser usado sem o
resto do catálogo. Como cada tabela foi feita, os intervalos e os limites estão em
[`compat/LEIA-ME.md`](../compat/LEIA-ME.md).

## A base e o "formato comum"

Um **contrato**, em programação, é a lista do que uma peça promete entregar à outra. Aqui, toda
base entrega em `corpus/colecoes/<nome>/documentos.parquet` uma tabela com estas colunas:

| Coluna | Obrigatória | Base do ACTD | Base do MAPE |
|---|---|---|---|
| `doc_uid` | sim | `ahu-brasil:<hash>` | `mape-v6:<doc_id>` |
| `reference_code` | sim | código do AHU (`PT/AHU/CU/…`) | o do MAPE, com zeros à esquerda; pode ser intervalo |
| `description` | sim | resumo impresso no catálogo do AHU | `doc_text_portuguese` |
| `folder` | sim | pasta do catálogo | nome da série, pela cifra de `ahu/conversor.py` |
| `new_code` | não | cota do Resgate impressa | calculada pelo conversor a partir do código |
| `old_code` | não | cota antiga impressa | preenchida pelo `compat/` (tabela de concordância) |
| `document_id_and_date` | não | número, data e lugar, como impressos | montada de `year`, `month`, `day` (sem lugar) |
| `ano_isolado` | não | ano inicial | `year` (nos intervalos de data, o MAPE dá o ano final) |
| `extracted_typology` | não | palavras em maiúsculas que abrem o resumo | a mesma regra |

E o `camada.json` da coleção diz qual é a base (`"base": "actd"` ou `"base": "mape"`).

Os dois adaptadores são:

- **ACTD:** `build/importar_colecao.py`, `build/importar_camadas.py` e
  `build/corrigir_com_lastro.py`, mais os acertos de cota do ACTD (`build/cotas.py`), que só valem
  para essa base;
- **MAPE:** `build/importar_base_mape.py`, que `scripts/montar_base_mape.py` roda junto com os
  passos seguintes.

Uma terceira base precisa só de um adaptador novo que entregue o formato comum. O núcleo e o
`compat/` não mudam.

## A construção

`build/construir_indice.py` calcula os vetores da busca por sentido (modelo
`intfloat/multilingual-e5-small`). Depois, `build/construir_app.py` junta a base, as camadas e o
`compat/` em `app_dados/`, e grava no manifesto a base usada, a versão do `compat/` e o SHA-256 de
cada arquivo. Para a base do ACTD, refazer a construção com este código dá os mesmos arquivos, byte
a byte, que a versão anterior à divisão em módulos.

---

**English summary.** The catalogue has three parts: the *core* (`ahu/`, `web/`: interface,
lexical and semantic search, shelfmark converter, PDF list), which only reads `app_dados/`; the
*compatibility module* (`compat/`, CC BY 4.0), which maps each AHU reference code to Projeto
Resgate images, DigitArq records and old shelfmarks and holds no summaries; and the *base* (the
catalogue entries and search vectors), which is kept outside the repository. Any dataset that
delivers the common format above can be plugged in: the author's ACTD base runs the public site,
and the open MAPE dataset can be used to reproduce it (`docs/REPRODUCE.md`).
