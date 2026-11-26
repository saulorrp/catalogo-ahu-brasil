# app_dados/

Os arquivos que o app lê, gerados por `python build/construir_app.py` a partir de `corpus/` e de
`compat/dados/`. Nada daqui vai para o repositório: dependem da base escolhida (ver
[`corpus/LEIA-ME.md`](../corpus/LEIA-ME.md)).

O app confere o `manifest.json` ao abrir: se um arquivo tiver SHA-256 diferente do registrado, ou se
o número de vetores não bater com o de documentos, ele para e diz o que reconstruir.

No servidor, esta pasta é montada no contêiner a partir da pasta de dados (ver
`deploy/SERVIDOR.md`).
