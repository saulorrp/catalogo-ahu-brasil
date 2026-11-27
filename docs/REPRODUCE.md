# Reproducing the catalogue with the open MAPE dataset

*Português: [`REPRODUZIR.md`](REPRODUZIR.md).*

This guide builds the Catálogo AHU-Brasil on your own computer from open data: the entries of the
MAPE dataset and the compatibility module in this repository. It exists for transparency and
reproducibility; it is not an installer.

The edition online (<https://catalogo-ahu.saulo-r.workers.dev/ahu/>) uses a different dataset,
built from the AHU catalogues published in the ACTD, which is not redistributed because the ACTD
terms do not allow an open licence. The MAPE edition is somewhat smaller, but search, access links,
the shelfmark converter and the PDF list are the same.

You need Python 3.11 or 3.12, about 3 GB of disk space, and `mape_dataset_version_6.csv` from
<https://doi.org/10.5281/zenodo.24403753> (Błoch et al., *MAPE: A Dataset of Correspondence from the
Portuguese Empire*, v6, 2026, CC BY 4.0).

```
python -m venv .venv
. .venv/bin/activate                 # Windows: .venv\Scripts\activate
pip install -r requirements-build.txt
python scripts/montar_base_mape.py --entrada dados/mape_dataset_version_6.csv
python -m uvicorn web.main:app --port 8000
```

The script checks the SHA-256 of the CSV (pass `--outra-versao` for another MAPE version), builds
the dataset (Brazil and River Plate series only; LLM-generated columns are left out), computes the
semantic-search vectors (about 40 minutes on 4 cores, resumable), links each entry to Projeto
Resgate and DigitArq through [`compat/`](../compat/LEIA-ME.md), and downloads the query models so the
app later runs offline.

Compared with the online edition (167,327 entries), the MAPE edition has 145,103 entries: MAPE does
not cover the Reino series, the Códices, Ultramar 035, Conselho Ultramarino 089 and a few smaller
series, and part of its entries describe several documents at once (`…/00009.00019`), as DigitArq
does. 96.6% of the MAPE entries link to a Projeto Resgate image. Details (in Portuguese, with English
summaries): [`BASE_MAPE.md`](BASE_MAPE.md) and [`MODULOS.md`](MODULOS.md).

Code: MIT. Compatibility module: CC BY 4.0. Entries and English translation: MAPE, CC BY 4.0, from the
AHU descriptions in DigitArq. No MAPE data is redistributed by this project.
