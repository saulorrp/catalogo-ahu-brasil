# Auditoria do banco contra o lastro

O lastro são as fontes primárias baixadas de novo: os PDFs do ACTD/IICT e as páginas e PDFs do gov.br. Estes
scripts conferem o banco contra elas e contra o MAPE, e montam um padrão ouro. Nenhum usa o parser da coleta
(`coleta/scripts/parse_actd.py`), para que a conferência seja independente.

```bash
python auditoria/extrair_actd.py LASTRO/actd extracao.jsonl          # verbetes dos PDFs do ACTD, cortados na cota
python auditoria/verificar_govbr.py LASTRO/govbr govbr.csv          # documentos do gov.br: o resumo está na página?
python auditoria/auditar.py --ouro extracao.jsonl --mape mape_dataset_version_6.csv \
       --govbr govbr.csv --saida SAIDA/                             # comparação e padrão ouro
```

Precisa do `pdftotext` (poppler). As saídas contêm os resumos do AHU e não vão para o repositório. O relatório de
21/11/2026 está na pasta do projeto, em `lastro/auditoria-2026-11-21/RELATORIO.md`.
