# Registro: cotas de Sergipe e cotas corrigidas (24/11/2026)

## O que mudou

1. **Sergipe (série 022) com a cota oficial.** As cotas dos 495 verbetes do inventário de Sergipe
   (gov.br) eram montadas pela numeração da edição impressa (9 caixas). No AHU e no DigitArq os
   documentos são numerados de 1 a 495, em 6 caixas: Cx. 1 = 1–106, Cx. 2 = 107–195,
   Cx. 3 = 196–287, Cx. 4 = 288–362, Cx. 5 = 363–432, Cx. 6 = 433–495
   (`coleta/scripts/parse_sergipe.caixa_oficial_022`). A numeração impressa fica em `old_code`
   (`AHU-Sergipe, cx. 02, doc. 16.`). Entraram os verbetes 107, 193 e 382, que o parser tinha
   perdido, e saiu do verbete 495 o rodapé da página. Feito pelo Antigravity em 24/11, 21h24–21h50
   (Londres), em `coleta/scripts/corrigir_sergipe.py`; conferido depois em 25 cotas no DigitArq.
2. **Nenhuma cota sem link.** `corpus/cotas_reconstruidas.ignore` fica vazio.
3. **Cotas corrigidas com prova** (`corpus/cotas_corrigidas.tsv`, 14 documentos). A fonte imprime
   uma cota que no AHU é de outro documento:
   - 2 erros tipográficos do ACTD (`CU-BrasilGeral.pdf`, p. 39 e 40: `AHU_CU_022` no lugar de
     `AHU_CU_003`, verbetes 173 e 176 do Brasil-Geral);
   - 2 cotas que o nosso parser do catálogo temático leu da observação ("Obs.: ver consulta em
     AHU_ACL_CU_022, ..."); são cópias de verbetes do Brasil-Geral e entram também em
     `corpus/duplicatas.ignore`;
   - 10 verbetes de catálogos temáticos que imprimem `Cx. 2` para documentos de Sergipe que estão
     em outra caixa.
   As 14 foram conferidas no DigitArq (mesmo resumo na cota nova) e as 12 dos catálogos temáticos
   também na página do gov.br. Na construção do app (`build/cotas.aplicar_corrigidas`), a cota
   impressa vai para a coluna `cota_na_fonte`; `new_code`, referência, pasta e links passam a ser
   os certos. A ficha mostra a cota impressa e avisa da correção.
4. **Série 081 (pasta Sergipe).** Os 44 links do DocReader que a primeira versão da correção
   apagou voltaram (`coleta/scripts/juntar_docreader.py` agora só refaz as cotas 022 do rolo
   `022_SE`).

## Números (app_dados/manifest.json, "acertos")

| | antes (main dcc1823) | depois |
|---|---:|---:|
| documentos | 167.324 | 167.327 |
| com registro no DigitArq | 156.843 | 157.337 |
| com página no DocReader | 153.165 | 153.665 |
| cotas sem link | 491 | 0 |
| cotas corrigidas | 0 | 14 |
| duplicatas fora da busca | 188 | 236 |
| traduções do MAPE ligadas | 141.796 | 142.277 |
