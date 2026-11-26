# Varredura do DocReader do Projeto Resgate

Este é o mapa de cada documento do catálogo para a imagem dele no visualizador do Projeto Resgate (Biblioteca Nacional). Com ele, o botão "Imagem no Projeto Resgate" do app abre o documento certo, em vez do portal.

## O problema

As imagens dos microfilmes do Resgate ficam no DocReader da BN, e cada coleção (rolo) tem um código `bib`:

    https://resgate.bn.gov.br/docreader/DocReader.aspx?bib=017_RJ_AV&hf=resgate.bn.gov.br&pagfis=49044

`pagfis` é a página física dentro do rolo. Os catálogos em HTML do gov.br já trazem esse número para 13 capitanias (SC, RS, AL, CE, ES, GO, MT, PB, PI, RN, Rio Negro, SE). O app usava isso desde o PR #19 (cerca de 15,7 mil documentos). Os catálogos que só existem em PDF não trazem o número: Rio de Janeiro, São Paulo, Minas, Bahia, Pernambuco, Maranhão, Pará e outros.

## O que foi testado e descartado (12/11/2026)

| Ideia | Resultado |
|---|---|
| Links arquivados no Wayback Machine | Uns 700 URLs, quase nada do RJ. Serviu só para descobrir os códigos `bib` reais. |
| Tabela de microfilmes nos PDFs do gov.br | Não existe. O PDF do RJ só traz caixa → intervalo de documentos. |
| Abrir o rolo na página 1 | Pouco útil e sujeito a códigos `bib` incorretos. Descartado. |
| Busca do DocReader (`Pesq="Cx. 69, D. 6420"`) | Às vezes acerta, mas recusa números de um dígito ("Menos de 2 letras") e muitas vezes cai no documento errado. |
| Árvore "Pastas" (Telerik) por postback | Existe (Caixa → Doc.), mas só carrega a caixa da página atual, e os postbacks encadeados falharam. |

## O método que funciona

Cada página do DocReader traz, no HTML, o rótulo do documento a que pertence (`AHU_ACL_CU_017, Cx. 69\Doc. 6420`) e o campo `hPagFis`. Basta um GET por página, sem login:

1. Acha o número de páginas do rolo por busca binária (`max_<bib>.txt`).
2. Divide o rolo em 8 trechos, um por thread.
3. Em cada trecho, a partir do início de um documento, salta 3, 6, 12... páginas até o rótulo mudar. Depois volta por busca binária até a primeira página do documento seguinte. Dá uns 5 pedidos por documento, mesmo em rolos de 190 mil páginas.
4. Grava `caixa, doc, pagfis` na hora, em `parcial_<bib>_w<n>.tsv`.

A varredura acha todos os documentos que estão no rolo, inclusive os que o nosso catálogo não tem.

## Acesso e execução

- O servidor da BN só responde a IP brasileiro (requer acesso a partir do Brasil) e exige `User-Agent` de navegador comum nas requisições HTTP.
- O script `coleta/scripts/varrer_docreader.py` suporta retomada automática: coleções prontas (`resgate_pagfis_<bib>.tsv`) são puladas e as em andamento continuam do último documento gravado em cada trecho.
- Ritmo recomendado: cerca de 60 documentos por minuto com 8 threads (evitar aumentar para não provocar bloqueio).

Fila (19 rolos): `017_RJ_AV`, `023_SP_AV`, `012_CSRP`, `003_BG_AV`, `011_MG`, `015_PE`, `005_BA_AV`, `005_BA_CA`, `005_BA_LF`, `009_MA`, `013_PA`, `050_CS_AV`, `084_OU_AV`, `030_SP_AV`, `089_UL_AV`, `017-1_RJ`, `023-1_SP_MG`, `089_CU`, `022_SE`. Lista oficial de coleções: `docreader/docmulti.aspx?bib=resgate`.

## Do resultado ao app

No repositório:

1. Copiar `resgate_pagfis_<bib>.tsv` para `coleta/docreader/` (em `.tsv.gz` com `mtime=0`, junto de `sergipe_govbr_pagfis.tsv.gz` extraído da tabela HTML do `gov.br`).
2. `python coleta/scripts/juntar_docreader.py`: converte em referência CRAV (`PT/AHU/CU/017/0069/06420`), mapeia casos especiais (`089_UL_AV → 035`, `089_CU → 089`, sub-séries com 3 dígitos, `011_MG` via `old_code`, e `022_SE` combinando `document_id_and_date` no TSV do DocReader + `(caixa, doc, sufixo)` na tabela `gov.br`) e acrescenta ao `corpus/resgate_docreader.tsv.gz`. O que veio do gov.br fica como está; documento repetido fica com a primeira página.
3. Refazer `app_dados` com `build/construir_app.py` (atualizando `documentos.parquet` e `manifest.json`).
4. O app lê a coluna `resgate_docreader` (`017_RJ_AV#49044`) e `ahu/links.py` monta o link.

Código: `coleta/scripts/varrer_docreader.py` e `coleta/scripts/juntar_docreader.py`. Fontes: `coleta/FONTES.md`, seção 2.

## Situação final da varredura (14/11/2026 — 19/19 rolos concluídos)

Varredura concluída integralmente: **127.029** linhas mapeadas nos 19 `.tsv` (`126.334` referências novas adicionadas ao `corpus/resgate_docreader.tsv.gz`, totalizando `142.057` entradas no índice junto às `15.723` do gov.br).

| Rolo (`bib`) | Série CRAV | Páginas no rolo | Docs no TSV | Casados no catálogo | Cobertura da série |
|---|---|---:|---:|---:|---:|
| `003_BG_AV` (Brasil Geral) | `003` | 24.353 | 3.817 | 3.677 / 3.785 | 97,1% |
| `005_BA_AV` (Bahia Avulsos) | `005` | 172.151 | 16.967 | 16.944 / 19.612 | 86,4% |
| `005_BA_CA` (Bahia Castro e Almeida) | `005-001` | 73.404 | 3.015 | 2.828 / 7.993 | 35,4%* |
| `005_BA_LF` (Bahia Luísa da Fonseca) | `005-002` | 19.904 | 3.358 | 3.141 / 3.206 | 98,0% |
| `009_MA` (Maranhão) | `009` | 109.612 | 13.118 | 13.078 / 13.126 | 99,6% |
| `011_MG` (Minas Gerais) | `011` | 94.917 | 13.884 | 13.938 / 14.079 | 99,0%** |
| `012_CSRP` (Sacramento/Rio da Prata) | `012` | 9.910 | 1.224 | 657 / 673 | 97,6% |
| `013_PA` (Pará) | `013` | 103.089 | 11.197 | 11.155 / 12.687 | 87,9% |
| `015_PE` (Pernambuco) | `015` | 191.421 | 20.029 | 19.981 / 20.016 | 99,8% |
| `017_RJ_AV` (Rio de Janeiro Avulsos) | `017` | 156.333 | 20.954 | 20.914 / 21.025 | 99,5% |
| `017-1_RJ` (RJ Castro e Almeida) | `017-001` | 42.277 | 6.503 | 6.421 / 11.858 | 54,1%* |
| `022_SE` (Sergipe) | `022` | 3.346 | 494 | 536 / 542 | 98,9%*** |
| `023_SP_AV` (São Paulo Avulsos) | `023` | 18.770 | 1.383 | 1.376 / 1.386 | 99,3% |
| `023-1_SP_MG` (SP Mendes Gouveia) | `023-001` | 35.205 | 5.112 | 5.049 / 5.112 | 98,8% |
| `030_SP_AV` (Serviço de Partes) | `030` | 2.134 | 685 | 684 / 684 | 100,0% |
| `050_CS_AV` (Contratos do Sal) | `050` | 1.297 | 138 | 137 / 137 | 100,0% |
| `084_OU_AV` (Visita do Ouro) | `084` | 312 | 54 | 54 / 54 | 100,0% |
| `089_CU` (Sec. Conselho Ultramarino) | `089` | 12.344 | 2.019 | 2.002 / 2.021 | 99,1% |
| `089_UL_AV` (Avulsos Ultramar) | `035` | 14.147 | 3.078 | 2.945 / 3.048 | 96,6% |

\* *Em `005_BA_CA` e `017-1_RJ`, a própria BN agrupa intervalos inteiros de documentos sob um único rótulo de `Doc.` (ex.: `p.10` a `p.24` de `005_BA_CA` trazem todas o rótulo `Doc. 2`, saltando direto para `Doc. 10` na `p.26`).*
\*\* *Em `011_MG`, a `resgate_com_quadro` inclui também a conversão por `old_code` (`cx. N, doc. M`) e 1 entrada já vinda do gov.br.*
\*\*\* *Em `022_SE`, o rolo do DocReader usa 6 caixas e numeração contínua de verbete (`1..495`, incluindo `3-A`/`3-B`), enquanto o catálogo CRAV usa 9 caixas e numeração local por caixa. O casamento cruza `document_id_and_date` com `resgate_pagfis_022_SE.tsv.gz` e `(cx, doc, sufixo)` / `old_code` com a tabela HTML do `gov.br` (`sergipe_govbr_pagfis.tsv.gz`).*

No catálogo completo (`app_dados/documentos.parquet`), `resgate_com_quadro` subiu de **15.783** (`main`, 9,4%) → **42.407** (PR #34, 25,3%) → **141.298** (varredura de 19 rolos + Sergipe, 84,4%) → **150.790** de **167.344** documentos (**90,1%**) após o resgate por capilhas em `017-1_RJ` e `005_BA_CA`.

### Recuperação de `AGRUPAMENTO_BN` por OCR de capilhas (Fases 1 e 2, concluída em 16–17/11/2026)

Para resolver os blocos em `017-1_RJ` (`017-001`) e `005_BA_CA` (`005-001`) onde a BN agrupou dezenas/centenas de documentos sob um único rótulo HTML no DocReader (`coleta/scripts/juntar_capilhas.py`):
- **Fase 1:** 3.558/3.558 pastas de cabeçalho processadas (`017-1_RJ` e `005_BA_CA`).
- **Fase 2:** 1.643/1.643 pastas internas varridas (`52.362` páginas processadas por OCR, apenas `1` imagem ausente na origem: `005_BA_CA__p28431`).
- **Integração conservadora (`juntar_capilhas.py`):** **9.468** referências únicas e sem ambiguidade (`4.546` da Fase 1 + `4.922` da Fase 2, incluindo `7` desambiguadas com exatidão pela caixa da pasta; `24` colisões ambíguas descartadas por segurança) incorporadas a `corpus/resgate_docreader.tsv.gz` (`142.057 → 151.525`) e `app_dados/documentos.parquet` (`141.298 → 150.790`, **+9.492** linhas sem alterar nenhum vínculo prévio).

### Auditoria por amostragem e correção da Colônia do Sacramento (17/11/2026)

Uma auditoria sorteou 850 links e os conferiu na BN em 17/11: 100 do gov.br, 300 da varredura, 150 dos mapeamentos especiais e 300 das capilhas (guardadas para revisão visual). A conferência verificou o rótulo da página, se ela é a primeira do documento e se o documento não reaparece adiante no rolo. Fora o defeito abaixo, nenhum link errado apareceu nos 550 conferidos automaticamente.

**Defeito achado:** o rolo `012_CSRP` mistura documentos das séries 012, 059 (Brasil-Limites), 065 (Montevidéu), 066 (Buenos Aires) e 071, todos com a mesma numeração de caixa e documento. A varredura não gravava a série, então tudo virou 012. Nos pares repetidos valia a primeira página, em geral a da outra série. Resultado: 146 dos 657 links da série 012 abriam o documento errado.

**Correção (17/11):**
1. Releitura na BN da série das 1.224 páginas de início do rolo. `resgate_pagfis_012_CSRP.tsv.gz` passou a trazer as colunas `serie_rotulo` e `rotulo`: 662 páginas são da série 012, 289 da 059, 224 da 065, 22 da 066 e 27 da 071. As quatro séries extras batem 100% com cotas do catálogo.
2. `juntar_docreader.py` refaz as linhas dos rolos que têm `serie_rotulo` e manda cada uma para a série do rótulo.
3. `coleta/scripts/aplicar_indice_resgate.py` leva o índice à coluna `resgate_docreader` do `app_dados`, sem refazer os embeddings.

Com isso, 146 links da 012 foram trocados e 563 documentos das séries 059, 065, 066 e 071 ganharam link pela primeira vez. O total passou de 150.790 para **151.353** de 167.344 documentos com link. Conferência de 40 links alterados na BN: todos corretos.

Ficam fora desta leva (diagnosticados no levantamento do `gov.br`):
- **`AGRUPAMENTO_BN` (`10.634` antes da última integração, `10.602` em `005-001` + `017-001`):** imagens existem dentro de blocos rotulados por intervalo no DocReader (`p.4542–9918` na Cx. 9 de `017-1_RJ`, `p.17447–18085` na Cx. 36 de `005_BA_CA`).
- **`ACERVO_EUROPEU_SEM_RESGATE` (`8.087`):** séries do catálogo vindas do ACTD/acervo europeu sem rolo no `docmulti.aspx` (`059`, `065`, `066`, `071`, `076`, `081`, além de caixas ausentes sem PDF correspondente).
- **`LACUNA_MICROFILME_BN` (`5.650` auditados antes da incorporação final de `022_SE`):** caixas inteiras ausentes em rolos publicados (`005_BA_AV`, `013_PA` Cx. 44 confirmada ausente por sonda entre `p.27952` e `p.47820`, etc.; em `022_SE`, a aparente lacuna de `Cx. 7–9` no rótulo do rolo decorria da renumeração para `Cx. 1–6` e foi resolvida pelo verbete/`gov.br`).
- **`FORMATO_NAO_CAIXA_DOC` (`2.125`):** Códices (`reference_code = None`), que possuem `3.064` links no `gov.br`, mas não usam chave `Cx./Doc.` no índice atual.
- **`COTA_OCR_IRREGULAR` (`185`):** restos de OCR sem cota normalizada e coleções fora do catálogo (*Angola*, *Catálogos e Guias*, *IHGB*).

## Achados no DocReader

### Mapeamento crítico `bib` → série CRAV (`juntar_docreader.py`)
Conferência direta nas páginas do DocReader e em `app_dados/documentos.parquet` revelou seis pontos essenciais:
- **Sub-séries CRAV usam 3 dígitos** em `documentos.parquet`: **`005-001`**, **`005-002`**, **`017-001`** e **`023-001`** (não `-01`).
- **`089_UL_AV` (*Avulsos (ULT)*, 14.147 págs):** o HTML da BN traz erroneamente `AHU_ACL_CU_089`, mas as imagens pertencem à **`AHU_ACL_CU_035`** (Série **`035` — Ultramar**).
- **`089_CU` (*Secretaria do Conselho Ultramarino*, 12.344 págs):** corresponde à **`AHU_ACL_CU_089`** (Série **`089`**).
- **`005_BA_CA` (`005-001`) e `005_BA_LF` (`005-002`):** ambas trazem `AHU_ACL_CU_005` no HTML, exigindo mapeamento pelo `bib`; além disso, `005_BA_LF` traz 735 intervalos com `_` (`4_5`), tratados pelo primeiro número inteiro (`RE_DOC_INICIAL`).
- **`011_MG` (`011`, Minas Gerais):** os rótulos do DocReader reiniciam `Doc.` por caixa (`cx. 2, doc. 1`), igual ao `old_code`, enquanto `reference_code` usa numeração contínua (`00075`). `juntar_docreader.py` resolve `(caixa, doc) → reference_code` via `old_code` de `corpus/colecoes/*/documentos.parquet` (levando de 138 para **13.938** documentos casados).
- **`022_SE` (`022`, Sergipe):** combina verbete em `document_id_and_date` contra `resgate_pagfis_022_SE.tsv.gz` e `(cx, doc, sufixo)` / `old_code` contra `sergipe_govbr_pagfis.tsv.gz` (extraído da tabela HTML do `gov.br`), evitando o deslocamento causado por `D. 3-A`/`3-B` (**536 / 542** casados).

## Auditoria de 17–18/11/2026

2.550 links foram conferidos por amostragem, entre o rótulo da BN e a leitura das capilhas. Os erros achados foram corrigidos: o rolo `012_CSRP` e a regra 6 de `juntar_capilhas.py`. Com 95% de confiança, a taxa de links errados fica abaixo de 0,23%. O registro completo está em [`auditoria_2026-11.md`](auditoria_2026-11.md).

## Códices (21/11/2026)

Os Códices do Conselho Ultramarino ficam num rolo à parte, o `bib=CODICES` (122.949 páginas, 749 códices), que não aparece entre os rolos de avulsos da lista oficial. O rótulo de cada página é só o códice (`AHU_ACL_CU - Cod. 274`), sem fólio, e cada quadro é uma abertura do livro (verso à esquerda, recto à direita).

`corpus/resgate_codices.tsv` dá o primeiro e o último quadro dos 15 códices que o catálogo tem, obtidos por busca binária no rótulo. Os cinco inícios que as páginas de verbetes do gov.br já traziam (235, 255, 267, 277 e 586) conferem exatamente. `build/cotas.py` e `coleta/scripts/aplicar_indice_resgate.py` dão esse início a cada verbete do códice: 2.125 documentos, que antes não tinham link. O botão diz "Códice no Projeto Resgate" e avisa que o link abre na primeira página do volume.

Próximo passo é levar o link ao fólio. Nas amostras, o fl. N está no quadro `início + N` (Cód. 235: quadro 61 = fl. 60, quadro 111 = fl. 110; Cód. 267: quadro 100 = fl. 99). Mas há códices com menos quadros do que fólios (586) e outros com muito mais (258, 247), e por isso a regra precisa ser calibrada códice a códice antes de entrar.

A Série Reino não tem rolo no DocReader. Foram testados 20 nomes de `bib`, e a página do gov.br traz só o catálogo, sem link de imagem.

### Calibração dos fólios e caixa errada no rótulo (21/11/2026)

Foram lidos os fólios de 75 quadros (5 por códice). A regra "quadro k = fl. k-1" vale só nos Cód. 235, 267 e 610. Nos outros, o deslocamento muda ao longo do volume: há páginas de índice, quebras de numeração e, no 584, outro rolo no meio. Por isso os códices continuam com o link no início do volume até que se calibrem os trechos.

Na sondagem de 66 documentos sem link, a maioria dos achados tem a página certa, mas a BN rotula a caixa vizinha (`Cx. 144` para a 145). Nas séries de numeração contínua, o número do documento basta, e `coleta/scripts/casar_por_numero.py` liga 180 documentos assim: o número tem de ser único no rolo e na série, e a caixa pode diferir em no máximo 2. O mesmo script liga 44 verbetes da série 081 ("Sergipe"), que repetem verbetes da 022: a cota antiga do 081 é a referência da 022, e ele recebe o quadro dela. A auditoria na BN (21/11/2026) conferiu os 225 links da primeira versão e os 15 inícios de códice, todos OK; mostrou também que a tabela do gov.br repete a cota antiga de Sergipe, o que tinha posto 2 verbetes 081 no documento vizinho, já corrigidos. Os 10 casos que a sondagem e o script cobrem em comum deram o mesmo quadro.