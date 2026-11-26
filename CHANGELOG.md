# O que mudou

*English summary at the end.*

O código tem número de versão próprio (o do `CITATION.cff`). O depósito no Zenodo
(doi:10.5281/zenodo.18772666, que leva sempre à versão mais recente) tem a sua numeração.

## Código 2.0.0, Zenodo 4.0 (26/11/2026)

- **Catálogo em módulos** ([`docs/MODULOS.md`](docs/MODULOS.md)): núcleo, módulo de
  compatibilidade e base. O núcleo lê só `app_dados/`; a base fica fora do repositório.
- **Módulo de compatibilidade** (`compat/`, CC BY 4.0): as tabelas que ligam cada cota à imagem no
  Projeto Resgate, ao registro do DigitArq e à cota antiga, com o SHA-256 de cada uma. A tabela de
  concordância das cotas antigas (93.330 códigos) é nova.
- **Reprodução com dados abertos** ([`docs/REPRODUZIR.md`](docs/REPRODUZIR.md)): o catálogo pode
  ser montado com o dataset do MAPE v6 (`scripts/montar_base_mape.py`), com intervalos de
  documentos tratados pelo primeiro número ([`docs/BASE_MAPE.md`](docs/BASE_MAPE.md)).
- **Nenhuma base no repositório.** A base do ACTD, que o site usa, ficou numa pasta privada do
  autor ([`docs/BASE_ACTD.md`](docs/BASE_ACTD.md)). O histórico do repositório recomeçou num commit
  único, sem dados.
- **Erros de leitura do PDF corrigidos com prova** (`build/corrigir_com_lastro.py`): no site,
  7.553 documentos. O ano isolado sai da data do verbete, e não do número do documento.
- **O depósito no Zenodo** passa a ser só o código, o módulo de compatibilidade e as instruções.
  Nenhum resumo do ACTD e nenhum dado do MAPE vão nele.

## Código 1.0.0 (20/11/2026)

- Repositório novo, só com o núcleo público: busca, links de acesso, conversor de cotas e lista
  em PDF. As outras páginas da versão anterior (pessoas, amostras, painel) saíram.
- Tradução inglesa do MAPE, reproduzida sem alterações, e tradução própria onde o MAPE não
  traduz.

## Zenodo 3.0 e anteriores (até 08/2026)

Pacotes com os resumos do ACTD, sob embargo. Não devem ser abertos: ver
[`LICENSE-DATA.md`](LICENSE-DATA.md).

---

**English summary.** 2.0.0 / Zenodo 4.0 (26 Nov 2026): the catalogue is split into core,
compatibility module (CC BY 4.0) and a base kept outside the repository. It can be reproduced from
the open MAPE v6 dataset. The repository history was restarted without data. PDF reading errors
in the site's base were fixed against the source. The open Zenodo deposit holds only code,
compatibility module and instructions. 1.0.0 (20 Nov 2026): new public-core repository.
Zenodo 3.0 and earlier: embargoed packages with ACTD summaries.
