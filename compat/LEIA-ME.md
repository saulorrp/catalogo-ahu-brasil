# compat/ — o módulo de compatibilidade

*English summary at the end.*

Este módulo liga uma cota do Arquivo Histórico Ultramarino (AHU) ao lugar onde o documento pode
ser visto: a **imagem** no Projeto Resgate "Barão do Rio Branco" (o visualizador DocReader da
Biblioteca Nacional) e a **ficha** no DigitArq. Ele também dá a **cota antiga** de cada documento
(a numeração anterior do AHU), para o conversor de cotas.

É a parte do catálogo que este projeto produziu. Não traz nenhum resumo de documento: só códigos,
números de quadro e cotas. Por isso pode ser publicado com licença aberta (CC BY 4.0) e servir a
qualquer base que traga o código de referência do AHU (`PT/AHU/CU/<série>/<caixa>/<documento>`):

- a **base do ACTD**, que o site usa;
- a **base aberta do MAPE** (doi:10.5281/zenodo.24403753), para quem quiser reproduzir o
  catálogo (ver [`docs/REPRODUZIR.md`](../docs/REPRODUZIR.md));
- qualquer outra lista de cotas.

## As tabelas (`compat/dados/`)

| Tabela | Linhas | O que liga | De onde veio |
|---|---:|---|---|
| `resgate_docreader.tsv.gz` | 152.050 | código → rolo e quadro do DocReader (`004_AL`, `1`) | links das páginas de verbetes do gov.br e varredura do DocReader (`coleta/docreader/`) |
| `digitarq_referencias.tsv.gz` | 151.986 | a lista dos registros do DigitArq, caixa a caixa | `coleta/scripts/varrer_digitarq.py`, 23/10/2026 |
| `resgate_codices.tsv` | 15 | Códice → primeiro quadro no rolo `CODICES` | sondagem do DocReader, 21/11/2026 |
| `concordancia_cota_antiga.tsv.gz` | 93.330 | código → cota antiga | cotas impressas nos catálogos do ACTD |

O `camada.json` guarda a versão do módulo, a licença e o SHA-256 de cada tabela. O SHA-256 é a
"impressão digital" do arquivo: se um único caractere mudar, ela muda inteira. Os testes conferem
esses números (`tests/test_compat.py`).

## Como usar

```python
from compat import Tabelas, ligar

base, contagem = ligar(base, Tabelas.ler())            # base: um DataFrame com reference_code e new_code
base, contagem = ligar(base, Tabelas.ler(), cota_antiga=True)   # preenche old_code vazio
```

`ligar` acrescenta duas colunas:

- `referencia_digitarq`: o registro do DigitArq que contém o documento. O DigitArq descreve muitos
  documentos em intervalo (`…/0016/03265.03267`), e o intervalo dele nem sempre começa onde começa o
  da base: o documento recebe o registro que tem o seu número;
- `resgate_docreader`: rolo e quadro, como `004_AL#1`. O link sai daí:
  `https://resgate.bn.gov.br/docreader/DocReader.aspx?bib=004_AL&hf=resgate.bn.gov.br&pagfis=1`.

### Intervalos

O MAPE copia o DigitArq e descreve parte dos documentos em intervalo: `…/0001/00009.00019` quer
dizer "documentos 9 a 19 da caixa 1", em geral um documento e os seus anexos. Para eles:

- o quadro do Resgate é o do **primeiro número** do intervalo que tiver quadro;
- a cota antiga é a do primeiro número;
- o link do DigitArq é o próprio registro;
- intervalos com mais de 50 números, invertidos ou com letra (`01335.A`) só ganham o que o
  primeiro número der.

## Limites conhecidos

- O servidor da Biblioteca Nacional só responde a quem acessa do Brasil.
- Os Códices abrem na primeira página do volume, não no fólio.
- A Série Reino não tem rolo no DocReader.
- A cota antiga só existe para as séries cujos catálogos a imprimem.

## Licença e crédito

CC BY 4.0. Crédito:

> Pacheco Rocha, S. R. *Catálogo AHU-Brasil*, módulo de compatibilidade (2026).
> doi:10.5281/zenodo.18772666. CC BY 4.0.

As imagens são do Projeto Resgate "Barão do Rio Branco" (Biblioteca Nacional) e as fichas, do
DigitArq (Arquivo Histórico Ultramarino / DGLAB): o módulo só aponta para elas.

Para refazer a concordância e o `camada.json`: `python scripts/atualizar_compat.py`.

---

**English summary.** `compat/` is the compatibility module of the Catálogo AHU-Brasil. It maps each
AHU reference code to the image of the document in Projeto Resgate (DocReader, Biblioteca Nacional
do Brasil), to the DigitArq record and to the old shelfmark. It holds no document summaries, only
identifiers and frame numbers, and is released under CC BY 4.0. It works with any dataset that
carries the AHU reference code, including the open MAPE dataset (doi:10.5281/zenodo.24403753),
whose interval codes (`…/00009.00019`) are linked through their first number.
