# A base do site: os catálogos do AHU no ACTD

*English summary at the end.*

O site (<https://catalogo-ahu.saulo-r.workers.dev/ahu/>) usa uma base montada pelo autor a partir
dos catálogos que o Arquivo Histórico Ultramarino publica no Arquivo Científico Tropical Digital
(ACTD/IICT), completados pelas páginas do Projeto Resgate no gov.br. Ela tem 167.327 documentos.

## Por que ela não está aqui

Os termos do ACTD permitem usar os resumos para fins pessoais, educativos e de investigação, com
crédito, mas não permitem redistribuí-los sob licença aberta. Os textos do gov.br são CC BY-ND 3.0.
Por isso a base, os vetores da busca calculados a partir dela e a tradução inglesa própria ficam
fora do repositório e fora do depósito aberto.

O que é produção deste projeto e não tem resumo nenhum está aqui, com licença aberta: o código e
o módulo de compatibilidade (`compat/`).

## Como ela foi feita

- **Método:** [`docs/METODO_COLETA.md`](METODO_COLETA.md), e os scripts da coleta, como rodaram,
  em [`coleta/`](../coleta/).
- **Fontes:** os PDFs do ACTD, conferidos por SHA-256 (`coleta/fontes_checksums.tsv`).
- **Erros de leitura do PDF:** corrigidos só com prova, por `build/corrigir_com_lastro.py`, que
  registra cada troca com o valor antigo e o novo. O texto da fonte nunca é reescrito.
- **Montagem:** os comandos da base do ACTD estão em [`AGENTS.md`](../AGENTS.md), na seção de
  comandos.

## Acesso

A base fica numa pasta privada do autor, com o SHA-256 de cada arquivo. Para pesquisa ou
educação, nos termos do ACTD, peça acesso ao autor.

---

**English summary.** The public site runs on a base the author built from the AHU catalogues
published in the ACTD (167,327 documents). The ACTD terms allow personal, educational and research
use with credit, but not redistribution under an open licence, so this base, its search vectors
and the project's own English translation are kept out of this repository and out of the open
deposit. The method, the collection scripts and the source checksums are published. Researchers
may ask the author for access under the ACTD terms. The catalogue can be reproduced with open
data from the MAPE dataset (`docs/REPRODUCE.md`).
