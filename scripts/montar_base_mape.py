"""montar_base_mape.py — monta o catálogo sobre a base aberta do MAPE, do CSV ao app.

Roda, em sequência, os passos que já existem em `build/`:

1. `build/importar_base_mape.py`: lê o CSV do MAPE, confere a versão pelo SHA-256 e escreve a
   base no formato comum, com a tipologia e a tradução inglesa do MAPE, em `corpus/`;
2. `build/construir_indice.py`: calcula os vetores da busca por sentido (e5-small). É o passo
   longo: cerca de 40 minutos num computador de 4 núcleos. Se for interrompido, rode o mesmo
   comando de novo: ele continua de onde parou;
3. `build/construir_app.py`: liga cada verbete ao Projeto Resgate e ao DigitArq pelo módulo
   `compat/` e grava os arquivos que o app lê, em `app_dados/`;
4. baixa os modelos da consulta (ONNX), para o app funcionar depois sem internet.

Nada aqui é instalador: é um script Python comum. Se um passo falhar, a mensagem diz qual.
Ver `docs/REPRODUZIR.md`.

Uso: python scripts/montar_base_mape.py --entrada dados/mape_dataset_version_6.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--entrada", default=str(RAIZ / "dados" / "mape_dataset_version_6.csv"))
    ap.add_argument("--corpus", default=str(RAIZ / "corpus"))
    ap.add_argument("--saida", default=str(RAIZ / "app_dados"))
    ap.add_argument("--outra-versao", action="store_true",
                    help="aceita um CSV que não seja o da versão 6 (registrado no manifesto)")
    ap.add_argument("--sem-modelos", action="store_true",
                    help="não baixa agora os modelos da consulta (o app os baixa na 1ª busca)")
    a = ap.parse_args()
    corpus, saida = Path(a.corpus), Path(a.saida)

    from build import construir_app, construir_indice, importar_base_mape
    from build.importar_base import ErroImportacao

    try:
        print("1/4 Base do MAPE ...")
        r = importar_base_mape.importar(Path(a.entrada), corpus, exigir_v6=not a.outra_versao)
        print("    " + ", ".join(f"{k}={v}" for k, v in r.items()))

        print("2/4 Vetores da busca por sentido (o passo longo) ...")
        modelo = construir_indice.MODELO_PADRAO
        encoder = construir_indice.criar_encoder(modelo, 64, None)
        construir_indice.construir_indice(corpus, None, modelo, encoder, desativar_outras=True)

        print("3/4 Ligação com o Resgate e o DigitArq (compat/) e arquivos do app ...")
        r = construir_app.construir(corpus, saida)
        print(f"    {r['documentos']} documentos em {saida}")
    except ErroImportacao as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 1

    if not a.sem_modelos:
        print("4/4 Modelos da consulta ...")
        try:
            from ahu import consulta_onnx
            from ahu.dados import carregar_sem_cache

            consulta_onnx.criar_encoder_de_dados(carregar_sem_cache(saida), log=print)
        except Exception as e:  # sem internet agora: o app baixa na primeira busca
            print(f"    aviso: modelos não baixados ({e}). O app tenta de novo na primeira busca.")
    print("Pronto. Abra com:  python -m uvicorn web.main:app --port 8000")
    return 0


if __name__ == "__main__":
    sys.exit(main())
