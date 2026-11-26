# Reproduzir o catálogo com a base aberta do MAPE

*English: [`REPRODUCE.md`](REPRODUCE.md).*

Este guia monta o Catálogo AHU-Brasil no seu computador a partir de dados abertos: os verbetes do
dataset do projeto MAPE e o módulo de compatibilidade deste repositório. Ele existe para
transparência e reprodutibilidade, e não é um instalador.

A edição que está no ar (<https://catalogo-ahu.saulo-r.workers.dev/ahu/>) usa outra base, montada
a partir dos catálogos que o AHU publica no ACTD. Essa base não é redistribuída, porque os termos
do ACTD não permitem licença aberta. A edição com o MAPE é **um pouco menor** (ver o fim deste
guia), mas a busca, os links, o conversor e a lista em PDF são os mesmos.

## O que você precisa

- Python 3.11 ou 3.12, e cerca de 3 GB livres em disco.
- O arquivo `mape_dataset_version_6.csv`, baixado de
  <https://doi.org/10.5281/zenodo.24403753> (Błoch, A.; Vasques Filho, D.; Bojanowski, M.; Santana,
  C.; Hussain, S.; Rzońca, A.; Podsiadły, A. *MAPE: A Dataset of Correspondence from the Portuguese
  Empire*, v6, 2026, CC BY 4.0).
- Internet durante a montagem, para baixar as bibliotecas e os modelos. Depois, o catálogo roda sem
  internet; só os links para o Resgate e o DigitArq abrem sites de fora.

## Os comandos

```
# 1. Na pasta do código (o zip do Zenodo ou um clone do repositório):
python -m venv .venv
. .venv/bin/activate                 # no Windows: .venv\Scripts\activate
pip install -r requirements-build.txt

# 2. Ponha o CSV do MAPE em dados/  e monte a base:
python scripts/montar_base_mape.py --entrada dados/mape_dataset_version_6.csv

# 3. Abra o catálogo:
python -m uvicorn web.main:app --port 8000
```

O catálogo abre em <http://localhost:8000>.

O **ambiente virtual** (`.venv`) é uma pasta com um Python e bibliotecas só deste projeto, para não
misturar com outros programas do computador.

## O que o passo 2 faz

1. **Confere o arquivo.** Calcula o SHA-256 do CSV (a "impressão digital" do arquivo) e para se não
   for o da versão 6. Para usar outra versão do MAPE, acrescente `--outra-versao`: ela fica
   registrada no `corpus/manifest.json`.
2. **Monta a base** (`build/importar_base_mape.py`). Fica com os verbetes das séries do Brasil e do
   Rio da Prata. Tira as colunas geradas por modelo de linguagem (remetente, destinatário, tópicos)
   e o `doc_type`. A tipologia sai das palavras em maiúsculas que abrem o resumo.
3. **Calcula os vetores da busca por sentido** (`build/construir_indice.py`, modelo
   `multilingual-e5-small`). É o passo longo: cerca de **40 minutos** num computador de 4 núcleos.
   Se for interrompido, rode o mesmo comando de novo, e ele continua de onde parou.
4. **Liga cada verbete ao Resgate e ao DigitArq** pelo módulo [`compat/`](../compat/LEIA-ME.md), e
   grava em `app_dados/` os arquivos que o app lê (`build/construir_app.py`).
5. **Baixa os modelos da consulta**, para o app funcionar depois sem internet.

Se algo falhar, a mensagem diz qual passo refazer.

## O que muda em relação à edição do site

Números de 26/11/2026, MAPE v6 contra a base do ACTD:

| | Base do ACTD (site) | Base do MAPE |
|---|---:|---:|
| Verbetes | 167.327 | 145.103 |
| Com link para a imagem no Resgate | 91,8% | cerca de 96% |
| Tradução inglesa | MAPE + tradução própria | a do MAPE |

O que a base do MAPE não tem:

- **Séries que o MAPE não cobre:** Reino (7.460 verbetes no ACTD), Códices (2.125), Ultramar 035
  (3.048), Conselho Ultramarino 089 (2.021), Serviço de Partes 030 (684) e outras menores.
- **Intervalos.** Parte dos verbetes descreve vários documentos juntos, como no DigitArq
  (`…/00009.00019`: um documento e os anexos). A cota aparece como `D. 9-19`, e a busca por
  `D. 12` acha o intervalo.
- **Data.** O MAPE dá o ano final dos intervalos de data e não traz o lugar.

## Arquivos e licenças

- Código: MIT. Módulo de compatibilidade: CC BY 4.0.
- Verbetes e tradução inglesa: do MAPE, CC BY 4.0, que reproduz as descrições do AHU no DigitArq.
  Cite o MAPE e o Arquivo Histórico Ultramarino.
- Nada da base do MAPE é redistribuído por este projeto: o CSV vem sempre do Zenodo do MAPE.
