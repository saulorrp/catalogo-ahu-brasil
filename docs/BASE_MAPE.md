# A base aberta: o dataset do MAPE

*English summary at the end.*

Este é o único arquivo do catálogo que trata do MAPE. Se o arranjo com o projeto mudar, muda este
arquivo, e o resto continua valendo.

## O dataset

> Błoch, A.; Vasques Filho, D.; Bojanowski, M.; Santana, C.; Hussain, S.; Rzońca, A.;
> Podsiadły, A. *MAPE: A Dataset of Correspondence from the Portuguese Empire*. Projeto Mapping
> the Atlantic Portuguese Empire. Zenodo, versão 6, 2026. doi:10.5281/zenodo.24403753. CC BY 4.0.

- Arquivo usado: `mape_dataset_version_6.csv`.
- SHA-256 esperado: `571d8c5a5f0d47c325bc9ed6a1f7c75ab3642ede764ab6992f0fe51442324beb`. O
  SHA-256 é a "impressão digital" do arquivo: `scripts/montar_base_mape.py` o confere e para se o
  arquivo for outro. Outra versão do MAPE entra com `--outra-versao` e fica registrada no
  manifesto.
- **Este projeto não redistribui nada do MAPE.** O CSV vem sempre do Zenodo do MAPE, baixado por
  quem reproduz o catálogo.

## O que o catálogo usa e o que deixa de fora

| Do MAPE | No catálogo |
|---|---|
| `reference_code` | código de referência, com zeros à esquerda; os intervalos ficam como estão |
| `doc_text_portuguese` | o resumo |
| `doc_text_english` | a tradução inglesa, sem alterações |
| `year`, `month`, `day` | a data e o filtro por período |
| `doc_id` | o identificador interno (`mape-v6:<doc_id>`) |
| `sender_name`, `receiver_name`, tópicos e *clusters* | **não usados**: foram gerados por modelo de linguagem |
| `doc_type` | **não usado**: a tipologia sai do próprio resumo, pela mesma regra da base do ACTD |

O catálogo acrescenta, pelo módulo [`compat/`](../compat/LEIA-ME.md), o link para a imagem no
Projeto Resgate, o registro do DigitArq e a cota antiga.

## Os números da montagem

Montagem de 26/11/2026, com o MAPE v6. Os números saem do próprio `montar_base_mape.py` e do
`app_dados/manifest.json` que ele grava.

| | |
|---|---:|
| Registros no CSV | 182.490 |
| Fora das séries do Brasil e do Rio da Prata | 37.387 |
| **Verbetes no catálogo** | **145.103** |
| … que descrevem um intervalo de documentos | 11.085 |
| … com intervalo que não se abre (invertido, com letra ou com mais de 50 números) | 70 |
| … sem tipologia (o resumo não começa pela espécie) | 4.384 |
| Com link para a imagem no Resgate | 140.099 (96,6%) |
| Com registro no DigitArq | 145.074 (quase 100%) |
| Com cota antiga (pela tabela de concordância) | 87.357 (60,2%) |

## Comparação com a base do site

O site usa outra base, montada pelo autor a partir dos catálogos do AHU no ACTD (167.327
documentos). Abrindo cada intervalo do MAPE nos números que ele cobre, 150.030 dos 167.327
documentos (89,7%) têm verbete correspondente no MAPE. A maior parte da diferença está em séries
que o MAPE não inclui:

| Série | Documentos na base do site |
|---|---:|
| Reino (076) | 7.460 |
| Ultramar (035) | 3.048 |
| Códices | 2.125 |
| Conselho Ultramarino (089) | 2.021 |
| Serviço de Partes (030) | 684 |
| Outras séries menores e verbetes sem cota legível | 428 |
| **Subtotal** | **15.766** |

Outros 1.531 documentos estão em séries que as duas bases têm. A diferença entre as duas não diz
qual delas erra. As duas descrevem o mesmo acervo por caminhos diferentes: o MAPE reproduz o
DigitArq, e a base do site reproduz os catálogos impressos.

Outras diferenças:

- **Intervalos.** Parte dos verbetes do MAPE descreve vários documentos juntos, como no DigitArq
  (`…/00009.00019`: um documento e os anexos). A cota aparece como `D. 9-19`, e a busca por `D. 12`
  acha o intervalo.
- **Data.** Nos intervalos de data, o MAPE dá o ano final, e o site, o inicial. O MAPE não traz o
  lugar.
- **Tradução inglesa.** É a do MAPE. O site usa a do MAPE e, onde ela não existe, uma tradução
  própria.

## Licença e crédito

O MAPE é distribuído sob CC BY 4.0. O texto dos verbetes reproduz as descrições do Arquivo
Histórico Ultramarino no DigitArq. Quem usar a edição montada com o MAPE deve citar o MAPE (acima)
e o Arquivo Histórico Ultramarino. O site, montado assim, mostra esse crédito no rodapé e na
página "Sobre".

---

**English summary.** The open edition of the catalogue is built from the MAPE dataset, version 6
(doi:10.5281/zenodo.24403753, CC BY 4.0), which users download from MAPE's own Zenodo record: this
project redistributes none of it. The LLM-generated fields (sender, receiver, topics) and
`doc_type` are not used. The 26 Nov 2026 build has 145,103 entries for the Brazil and Río de la
Plata series. 96.6% of them link to a Projeto Resgate image through the compatibility module.
Compared with the author's ACTD-based site (167,327 documents), 89.7% of documents are covered.
Most of the gap is series MAPE does not include (Reino, Ultramar 035, Códices, 089, 030).
