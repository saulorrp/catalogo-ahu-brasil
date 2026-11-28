# Catálogo AHU-Brasil

Busca no catálogo do Arquivo Histórico Ultramarino (AHU) para o Brasil colonial:
**167.327 documentos** do Conselho Ultramarino, de 1401 a 1897, em 33 pastas. O catálogo leva o
pesquisador de uma pergunta a um conjunto de cotas que ele possa justificar, citar e pedir no
arquivo, e de cada cota às imagens do documento no Projeto Resgate.

**Ele não contém as imagens dos manuscritos.** O que ele tem são os resumos publicados pelo AHU, as
cotas e os links para onde o documento pode ser visto.

## O que o catálogo faz

No ar em **<https://catalogo-ahu.saulo-r.workers.dev/ahu/>**.

- **Busca híbrida.** Uma rota de cotas (as três formas de citar um documento levam a ele), BM25 por
  campos e busca semântica com `multilingual-e5-small`, fundidas por posição. No servidor, um
  reranker (cross-encoder mMiniLM) relê os 30 primeiros resultados; a lista aparece antes e se
  reordena quando ele termina. Filtros por período, pasta e tipologia.
- **Resumo em inglês.** A tradução publicada pelo projeto
  [MAPE](https://doi.org/10.5281/zenodo.24403753) (Mapping the Atlantic Portuguese Empire; Błoch,
  Vasques Filho, Bojanowski, Santana, Hussain, Rzońca e Podsiadły, 2026, CC BY 4.0), reproduzida
  sem alterações e mostrada quando o resumo português do MAPE é o mesmo do catálogo. Onde o MAPE não
  traduz, uma tradução automática do próprio catálogo (Google Gemini, glossário fixo de tipologias,
  [`coleta/traducao_en/`](coleta/traducao_en/)), marcada como tal.
- **Links de acesso.** Cada documento leva ao DigitArq (ficha do AHU), ao DocReader da Biblioteca
  Nacional (imagens do Projeto Resgate, para 90% dos documentos) e à página do catálogo do AHU no
  ACTD de onde o resumo foi tirado.
- **Conversor de cotas.** Código de referência (`PT/AHU/CU/…`), cota do Resgate (`AHU_ACL_CU_…`) e
  cota antiga (`AHU-<região>, cx., doc.`) convertidos entre si, também para cotas de fora do
  catálogo. A cota antiga só se converte pela base, salvo Castro e Almeida e Mendes Gouveia, que
  guardam a numeração atual.
- **Lista de arquivos selecionados, em PDF.** A seleção atravessa buscas e vira a folha que se leva ao
  arquivo: ano, cota, código de referência, resumo, link do DigitArq e uma caixa para marcar.

## De onde vêm os dados

- **Coleta.** Os resumos e as cotas vêm dos catálogos que o próprio AHU publica em PDF de texto no
  [ACTD](https://actd.iict.pt/). As páginas do
  [Projeto Resgate](https://www.gov.br/bn/pt-br/central-de-conteudos/projeto-resgate) no gov.br
  foram rastreadas e salvas como vieram: dão o link de cada documento, conferem o texto do ACTD e
  cobrem Códices, parte da Série Reino e Sergipe.
- **Catálogos só escaneados.** Bahia, São Paulo, Minas Gerais e Pará só existiam no Resgate como
  imagens do catálogo impresso, e Pernambuco, Maranhão e Colônia como PDFs com OCR pouco
  confiável. Essas páginas foram transcritas automaticamente (Gemini Flash, transcrição literal;
  páginas recusadas passaram pelo Tesseract e foram corrigidas olhando a imagem). Quando se achou o
  texto nativo do AHU no ACTD, ele virou a fonte, e a transcrição passou a servir de conferência:
  em 61 mil verbetes comparados pela cota, o texto confere em 97%
  ([relatório](coleta/qc/RELATORIO_CONFERENCIA_OCR.md)).
- **Cura das cotas.** O conversor ([`ahu/conversor.py`](ahu/conversor.py)) reconhece as variantes
  das fontes (`AHU_CU_` sem `ACL`, `0005-01`, `D. 20.836`), normaliza numa chave
  série/caixa/documento e calcula a cota do Resgate e o código de referência. As cotas repetidas e
  os verbetes sem cota ficaram como na fonte, com aviso, em vez de receberem um número adivinhado.
- **Controle de qualidade.** 4.424 verbetes (2,6%) têm alguma marca (sem data, cota repetida, fora
  de sequência, texto divergente entre ACTD e Resgate). O texto nunca é alterado pela marca.
- **Tipologia.** A primeira palavra do resumo (CARTA, OFÍCIO, REQUERIMENTO…) é extraída e
  normalizada. Uma forma é canônica quando aparece em pelo menos cinco documentos; as outras ficam
  "a revisar" e não entram no filtro.
- **Proveniência.** Cada documento traz a citação da fonte, o PDF e a página do ACTD e a página do
  Resgate. Nenhum resumo foi escrito ou reescrito por IA.

O passo a passo completo, com números e decisões, está em
[`docs/METODO_COLETA.md`](docs/METODO_COLETA.md), e os scripts da coleta, publicados como rodaram,
em [`coleta/`](coleta/). Fontes e links também na aba **Sobre** do catálogo.

## Como o repositório está organizado

O catálogo tem três partes, e só duas delas estão aqui ([`docs/MODULOS.md`](docs/MODULOS.md)):

| Parte | O que é | Onde está |
|---|---|---|
| **Núcleo** | a interface, a busca, o conversor de cotas e a lista em PDF | `ahu/`, `web/`, `build/` |
| **Módulo de compatibilidade** | as tabelas que ligam cada cota à imagem no Projeto Resgate, à ficha do DigitArq e à cota antiga: produção deste projeto, sem nenhum resumo | [`compat/`](compat/LEIA-ME.md) (CC BY 4.0) |
| **Base** | os verbetes (resumo, cotas, data) e os vetores da busca | **fora do repositório** |

Há duas bases possíveis:

- **ACTD**, a do site: montada a partir dos catálogos que o AHU publica no ACTD. Os termos do ACTD
  não permitem redistribuir os resumos sob licença aberta, e por isso ela fica só numa pasta privada
  do autor, fora de servidores de terceiros, e é cedida a pedido para pesquisa. As versões 1.0 e
  2.0 do registro no Zenodo, de acesso restrito, são do experimento anterior, restrito à
  Macrorregião Sul, e não contêm esta base.
- **MAPE**, aberta: os verbetes do dataset do projeto MAPE (CC BY 4.0). Qualquer pessoa pode montar
  o catálogo com ela seguindo [`docs/REPRODUZIR.md`](docs/REPRODUZIR.md). A edição fica um pouco
  menor (145.103 verbetes), sem a Série Reino, os Códices e outras séries que o MAPE não cobre
  ([`docs/BASE_MAPE.md`](docs/BASE_MAPE.md)).

Por que a base do ACTD não é publicada, e como foi feita: [`docs/BASE_ACTD.md`](docs/BASE_ACTD.md).
O que mudou de versão a versão: [`CHANGELOG.md`](CHANGELOG.md).

## Rodar no seu computador

Python 3.11 ou 3.12. Com a base do MAPE:

```
pip install -r requirements-build.txt
python scripts/montar_base_mape.py --entrada dados/mape_dataset_version_6.csv
python -m uvicorn web.main:app --port 8000
```

O catálogo abre em <http://localhost:8000> e lê só a pasta `app_dados/`. O passo a passo, com o
que cada comando faz, está em [`docs/REPRODUZIR.md`](docs/REPRODUZIR.md). O reranker liga com
`AHU_RERANKER=1`; sem ele, a busca é a híbrida. Para o servidor (Docker), veja
[`deploy/SERVIDOR.md`](deploy/SERVIDOR.md), e para os detalhes de manutenção,
[`AGENTS.md`](AGENTS.md).

## Licença

- **Código: MIT** ([`LICENSE`](LICENSE)).
- **Módulo de compatibilidade: CC BY 4.0** ([`compat/LEIA-ME.md`](compat/LEIA-ME.md)).
- Dados: **licença por camada** ([`LICENSE-DATA.md`](LICENSE-DATA.md)): fatos e identificadores
  CC0, camadas próprias CC BY 4.0, base do MAPE CC BY 4.0 (dos autores do MAPE), resumos do ACTD
  fora da licença aberta e fora do repositório.
- Fonte embutida no PDF: **Noto Serif** (SIL OFL), em
  [`ahu/fontes/LICENSE-NotoSerif-OFL.txt`](ahu/fontes/LICENSE-NotoSerif-OFL.txt).
- Resumos e cotas do catálogo: Arquivo Histórico Ultramarino e Projeto Resgate
  "Barão do Rio Branco".
