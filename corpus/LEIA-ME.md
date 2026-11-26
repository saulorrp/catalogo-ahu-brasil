# corpus/

Pasta de trabalho da **base** que o catálogo vai usar. Nada daqui vai para o repositório.

O que fica aqui depois de montar uma base:

```
corpus/
  manifest.json                      as coleções e camadas da base, com o SHA-256 de cada arquivo
  colecoes/<colecao>/documentos.parquet   uma linha por documento (resumo, cotas, data)
  colecoes/<colecao>/camada.json          de onde a base veio (e o campo "base": "mape" ou "actd")
  camadas/tipologia_v1/              a tipologia tirada do resumo
  camadas/embeddings_e5small_v1/     os vetores da busca por sentido
  camadas/mape_en_v6/                a tradução inglesa (na base MAPE, a do próprio MAPE)
```

Há duas bases:

- **MAPE** (aberta, CC BY 4.0): `python scripts/montar_base_mape.py --entrada dados/mape_dataset_version_6.csv`
  monta tudo aqui e em `app_dados/`. Ver [`docs/REPRODUZIR.md`](../docs/REPRODUZIR.md).
- **ACTD** (a do site): os resumos são do AHU, publicados no ACTD, e os termos do ACTD não permitem
  redistribuí-los sob licença aberta. A base fica numa pasta privada do autor e num registro de
  acesso restrito no Zenodo. Com ela em mãos, use `--corpus <pasta da base>/corpus` nos scripts de
  `build/`.

As tabelas que ligam as cotas ao Projeto Resgate e ao DigitArq **não** ficam aqui: estão em
[`compat/`](../compat/LEIA-ME.md), porque servem a qualquer base.
