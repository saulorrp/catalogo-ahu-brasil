# O catálogo no servidor próprio

O GitHub publica a imagem do app (`ghcr.io/saulorrp/catalogo-ahu-brasil`, pública) a cada mudança no
`main`. O servidor roda essa imagem e se atualiza sozinho (Watchtower, de hora em hora). O
endereço público vem do **Tailscale Funnel**, sem abrir portas no roteador e sem expor o IP de casa.

O endereço público do catálogo é **https://catalogo-ahu.saulo-r.workers.dev/ahu/**: um Worker da
Cloudflare recebe as visitas e as repassa ao servidor. É esse endereço que se divulga e se cita;
o endereço do Funnel fica só como origem do Worker, fora da documentação.

O compose liga o reranker (`AHU_RERANKER=1`, ver `docs/plano_busca_servidor.md`).

Precisa de: Docker, ~3 GB de RAM livres para o app, ~2 GB de disco.

## Os dados

A imagem traz só o código e o módulo de compatibilidade: **nenhuma base**. A pasta `app_dados/`
da base que o servidor vai servir fica no disco do servidor e é montada no contêiner, só para
leitura, pela variável `AHU_APP_DADOS` do compose:

- no site, a base do ACTD, na pasta privada do autor
  (`eins-project/catalogo-ahu-brasil-dados-actd/app_dados`);
- numa reprodução, a base do MAPE montada por `scripts/montar_base_mape.py`.

Para trocar os dados, reconstrua a pasta e reinicie o contêiner (`docker compose up -d
--force-recreate`). O app confere os hashes do `manifest.json` ao abrir e não sobe com dados
desalinhados.

## Uma vez só

1. **Pasta e compose.** `mkdir -p ~/catalogo-ahu` e copie para lá o `docker-compose.yml` desta
   pasta. Crie ao lado um `.env` com `AHU_APP_DADOS=/caminho/da/base/app_dados`.
2. **Modelos.** Na primeira busca o app baixa o e5 e o reranker do Hugging Face para o volume
   `catalogo-ahu_modelo` (~1 GB). Se a rede da casa cortar o download no meio, baixe com `curl`
   (que retoma) e copie para o volume, mantendo a forma `<dono>__<repositório>/<arquivo>`:

       Xenova__multilingual-e5-small/{model.onnx,tokenizer.json}
       cross-encoder__mmarco-mMiniLMv2-L12-H384-v1/{model_quint8_avx2.onnx,tokenizer.json}

3. **Funnel.** O app escuta só em `127.0.0.1:8502` e serve em `/ahu` (`AHU_ROOT_PATH`). Publique esse caminho:

       sudo tailscale funnel --bg --set-path /ahu http://127.0.0.1:8502/ahu

   O Funnel guarda a configuração e volta sozinho depois de reiniciar a máquina.

## Subir

    cd ~/catalogo-ahu && sudo docker compose up -d

Para conferir: `curl -s https://catalogo-ahu.saulo-r.workers.dev/ahu/saude` (ou, no próprio
servidor, `curl -s http://127.0.0.1:8502/ahu/saude`) responde
`{"status":"ok",…}` com o número de documentos, a versão dos dados e o commit.

Ao subir, o app carrega os modelos e faz uma busca de aquecimento em segundo plano, para a
primeira pessoa não pagar a carga (`AHU_SEM_AQUECIMENTO=1` desliga). `AHU_RERANKER_TOPO`
(padrão 30) e `AHU_RERANKER_TOKENS` (padrão 192) ajustam o reranker sem mexer no código; as
medidas estão em `docs/plano_busca_servidor.md`.

## O freio das buscas

Uma busca nova custa de 2 a 3 segundos de processador. Para que um robô ou um ataque não ocupe a
máquina inteira, o app limita as buscas (`web/limite.py`): cada visitante faz até 60 pedidos de
busca por minuto (`AHU_LIMITE_POR_MINUTO`), e só 2 buscas rodam ao mesmo tempo
(`AHU_BUSCAS_SIMULTANEAS`), com as outras numa fila de até 20 (`AHU_FILA_MAXIMA`) por até 15
segundos (`AHU_ESPERA_MAXIMA`). Acima disso o app responde 429 com uma página que pede para esperar.
Fichas, páginas fixas e a página inicial nunca são freadas. O visitante é reconhecido pelo
cabeçalho `X-Visitante-IP`, que o Worker preenche com o IP real. `AHU_LIMITE=0` desliga o freio.

## Modo anônimo

Para a avaliação cega de um artigo sobre o catálogo, o site pode esconder a autoria. Com
`AHU_ANONIMO=1`:

- o rodapé e a aba Sobre trocam o crédito ("Pacheco Rocha, S. R., [...], doi:10.5281/zenodo.18772666")
  por "Autoria omitida para a avaliação cega";
- os links para o GitHub (aba Referências e aba Sobre) viram texto sem link;
- o botão "Reportar erro" aparece desativado, com a explicação "Desativado para revisão cega" ao
  passar o mouse (a página não leva o e-mail nem o endereço público do site).

O nome não fica escondido na página: ele não é enviado. Para ligar, no agiulfo, na pasta do
`docker-compose.yml`:

```
echo "AHU_ANONIMO=1" >> .env
docker compose up -d app
```

Para desligar, troque o 1 por 0 no `.env` e rode o mesmo `docker compose up -d app`. O teste
`tests/test_web.py::test_modo_anonimo_esconde_o_autor` confere as páginas nos dois modos.

## Tirar do ar

    sudo tailscale funnel --set-path /ahu off       # só o endereço público
    cd ~/catalogo-ahu && sudo docker compose down    # o app
