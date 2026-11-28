# Licenças por camada

Este repositório mistura material de origens e direitos diferentes. Cada camada tem a sua licença,
e só vale a licença da linha em que o arquivo está. Em caso de dúvida, a mais restritiva prevalece.

Desde 26/11/2026 **nenhuma base de verbetes fica neste repositório** (ver o `README.md`): só o
código e o módulo de compatibilidade. As linhas sobre os resumos valem para quem monta o catálogo
com uma das bases.

| Camada | Onde está | Licença |
|---|---|---|
| **Código** | `ahu/`, `web/`, `build/`, `compat/__init__.py`, `coleta/scripts/`, `avaliacao/`, `scripts/`, `tests/`, `Dockerfile`, `deploy/` | MIT ([`LICENSE`](LICENSE)) |
| **Módulo de compatibilidade** | `compat/dados/` (cota → Resgate, cota → DigitArq, cota → cota antiga) | CC BY 4.0, com o crédito abaixo ([`compat/LEIA-ME.md`](compat/LEIA-ME.md)) |
| **Fatos e identificadores** | `doc_uid`, cotas (Resgate, referência, antiga), série, caixa, documento, ano, local, links (DigitArq, DocReader, ACTD), página de origem, marcas de QC, `duplicata_de` | CC0 1.0 (fatos não são protegidos; a CC0 só remove dúvidas) |
| **Camadas próprias** | tipologia normalizada (`corpus/camadas/tipologia_v1`, gerada localmente), `avaliacao/`, `coleta/qc/`, documentação em `docs/` | CC BY 4.0, com o crédito abaixo |
| **Base do MAPE** (verbetes e tradução inglesa) | `corpus/colecoes/mape-v6/` e `corpus/camadas/mape_en_v6/`, gerados localmente a partir do CSV do MAPE (`scripts/montar_base_mape.py`); não redistribuídos por este projeto | CC BY 4.0, dos autores do MAPE: Błoch, A.; Vasques Filho, D.; Bojanowski, M.; Santana, C.; Hussain, S.; Rzońca, A.; Podsiadły, A. *MAPE: A Dataset of Correspondence from the Portuguese Empire*, v6, 2026, doi:10.5281/zenodo.24403753. O texto reproduz as descrições do AHU no DigitArq |
| **Resumos do catálogo do AHU** (via ACTD/IICT) | base do ACTD, **fora do repositório** (só na pasta privada do autor; cedida a pedido para pesquisa) | **Fora da licença aberta.** Termos do ACTD: uso livre só para fins pessoais, educativos e de investigação, com crédito; uso comercial exige autorização |
| **Textos do Projeto Resgate** (gov.br / Biblioteca Nacional) | parte da base do ACTD (Códices, Sergipe), fora do repositório | CC BY-ND 3.0 (licença do portal gov.br): cópia literal com crédito, sem alterar o texto |
| **Tradução inglesa do catálogo** | base do ACTD, fora do repositório (`traducao_en_catalogo_v1`) | CC BY 4.0. Tradução automática feita pelo catálogo com o Google Gemini (`coleta/traducao_en/`), só onde o MAPE não traduz; sem revisão. A tradução é de resumos do AHU, cujos termos (ACTD) também valem |
| **Derivados diretos dos resumos** | `app_dados/` e vetores em `corpus/camadas/embeddings_*`, sempre locais | Seguem os termos dos resumos de que derivam |

Os resumos nunca são reescritos: erros da fonte ficam como estão e ganham a marca `[sic]` só na
exibição. Correções, quando houver, vão para colunas separadas.

## Depósito aberto

Não há autorização do AHU nem da BN para redistribuir os resumos sob licença aberta. Por isso o
depósito aberto no Zenodo (a partir da versão 4.0, de 26/11/2026) traz **só o código, o módulo de
compatibilidade e as instruções** para montar o catálogo com a base aberta do MAPE
([`docs/REPRODUZIR.md`](docs/REPRODUZIR.md)). Nenhum resumo do ACTD e nenhum dado do MAPE vão
nele. A base do ACTD fica com o autor ([`docs/BASE_ACTD.md`](docs/BASE_ACTD.md)).

## Crédito exigido

> Dados derivados: Pacheco Rocha, S. R. *Catálogo AHU-Brasil* (2026), doi:10.5281/zenodo.18772666, CC BY 4.0.
> Catálogo de origem: Arquivo Histórico Ultramarino (Lisboa), catálogos publicados no Arquivo
> Científico Tropical Digital (ACTD/IICT), e Projeto Resgate "Barão do Rio Branco"
> (Biblioteca Nacional / Ministério da Cultura).
> Módulo de compatibilidade (links ao Resgate e ao DigitArq, cotas antigas): Pacheco Rocha, S. R.,
> *Catálogo AHU-Brasil* (2026), doi:10.5281/zenodo.18772666, CC BY 4.0.
> Tradução inglesa: projeto MAPE (Błoch, Vasques Filho, Bojanowski, Santana, Hussain, Rzońca e Podsiadły, 2026),
> doi:10.5281/zenodo.24403753, CC BY 4.0.

Quem hospedar o catálogo deve manter este crédito no rodapé do site.

## Histórico

- 12/11/2026: licença por camada, depois do parecer de direitos de uso. Substitui a CC BY 4.0
  "provisória" para todos os dados derivados, que relicenciava os resumos sem base para isso.
- 20/11/2026: repositório novo, só com o núcleo público (busca, links, conversor de cotas, PDF).
- 26/11/2026: catálogo em módulos. A base do ACTD sai do repositório; o módulo de compatibilidade
  (`compat/`) ganha licença própria (CC BY 4.0); o catálogo pode ser reproduzido com a base aberta
  do MAPE (`docs/REPRODUZIR.md`).
- 26/11/2026: o depósito aberto no Zenodo passa a ser só código, compatibilidade e instruções
  (versão 4.0); o pacote "sem os resumos" de 20/11 não é mais publicado.
