# Tradução inglesa dos resumos sem MAPE

Traduz, com o Gemini pela linha de comando `agy` (assinatura AI Pro, sem custo), os resumos que a
camada `mape_en_v6` não cobre: os que só existem no catálogo, os sem código de referência (Reino,
Códices) e os em que o resumo do MAPE é outro. Comando em [`PROMPT.md`](PROMPT.md); glossário fixo
de tipologias e cargos, inglês atual, nomes como na fonte, "galera" nunca vira "galley".

Na versão EN do catálogo essas traduções aparecem marcadas como tradução automática do catálogo,
separadas das do MAPE.

```
python coleta/traducao_en/traduzir.py preparar        # entrada/fila.jsonl.gz e entrada/piloto.jsonl.gz
python coleta/traducao_en/traduzir.py rodar --fila piloto --modelo <modelo>
python coleta/traducao_en/traduzir.py verificar --modelos <modelo> [<modelo>]
python coleta/traducao_en/traduzir.py comparar --modelos <modelo A> <modelo B>
```

`entrada/` e `saida/` não vão para o Git: a entrada se refaz com `preparar` (semente fixa) e a
saída vira camada do corpus.
