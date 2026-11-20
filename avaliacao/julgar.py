"""julgar.py — interface cega, no terminal, para julgar as consultas de ouro.

- Mostra os 20 primeiros resultados de cada consulta em ordem aleatória;
- O avaliador não vê a posição que a busca deu a cada documento;
- Julgamento em três níveis:
    0 = irrelevante
    1 = relevante
    2 = muito relevante
- Grava tempo de decisão por documento (delta_seconds) e salva em avaliacao/julgamentos.json;
- Permite retomar de onde parou.
"""
from __future__ import annotations

import argparse
import json
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ARQUIVO_CONSULTAS = Path(__file__).resolve().parent / "consultas_ouro.json"
ARQUIVO_JULGAMENTOS = Path(__file__).resolve().parent / "julgamentos.json"
ARQUIVO_POOL = Path(__file__).resolve().parent / "pool_candidatos.json"


def carregar_consultas(caminho: Path = ARQUIVO_CONSULTAS) -> list[dict[str, Any]]:
    """Carrega as 30 consultas do conjunto de teste."""
    with open(caminho, "r", encoding="utf-8") as f:
        return json.load(f)


def carregar_julgamentos_existentes(caminho: Path = ARQUIVO_JULGAMENTOS) -> dict[str, Any]:
    """Carrega julgamentos prévios para retomar."""
    if caminho.is_file():
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def salvar_julgamentos(dados: dict[str, Any], caminho: Path = ARQUIVO_JULGAMENTOS) -> None:
    """Salva estado atual dos julgamentos de forma atômica."""
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=2, ensure_ascii=False)


def construir_pool_candidatos(
    dados: Any,
    consultas: list[dict[str, Any]],
    top_k: int = 20,
    seed: int = 42,
) -> dict[str, Any]:
    """Coleta o top_k da busca para cada consulta e embaralha, para cegar o avaliador."""
    from ahu.busca import buscar

    pool: dict[str, Any] = {}
    rng = random.Random(seed)
    docs = dados.documentos

    for q_item in consultas:
        resposta = buscar(dados, q_item["consulta"])
        candidatos = []
        for r in resposta.resultados[:top_k]:
            linha = docs.iloc[r.linha]
            ano = linha.get("ano_isolado")
            candidatos.append({
                "uid": r.doc_uid,
                "reference_code": linha.get("reference_code"),
                "cota": linha.get("new_code"),
                "ano": int(ano) if pd.notna(ano) else None,
                "description": linha.get("description"),
            })
        rng.shuffle(candidatos)
        pool[q_item["id"]] = {
            "consulta": q_item["consulta"],
            "tipo": q_item["tipo"],
            "candidatos": candidatos,
        }

    return pool


def executar_julgamento_cli(
    pool: dict[str, Any],
    julgamentos_salvos: dict[str, Any],
    caminho_saida: Path = ARQUIVO_JULGAMENTOS,
) -> None:
    """Interface interativa de terminal para julgamento cego."""
    print("=" * 70)
    print("Classificador AHU — Auditoria Cega de Recuperação ")
    print("Pressione 0 (irrelevante), 1 (relevante), 2 (muito relevante) ou q (sair).")
    print("=" * 70)

    total_consultas = len(pool)
    for idx_q, (q_id, info_q) in enumerate(pool.items(), start=1):
        q_texto = info_q["consulta"]
        q_tipo = info_q["tipo"]
        candidatos = info_q["candidatos"]

        julg_q = julgamentos_salvos.setdefault(q_id, {
            "consulta": q_texto,
            "tipo": q_tipo,
            "julgamentos": {},
        })

        itens_a_julgar = [c for c in candidatos if c["uid"] not in julg_q["julgamentos"]]
        if not itens_a_julgar:
            continue

        print(f"\nConsulta [{idx_q}/{total_consultas}] ({q_tipo.upper()}): '{q_texto}'")
        print(f"Candidatos pendentes nesta consulta: {len(itens_a_julgar)}")

        for idx_c, cand in enumerate(itens_a_julgar, start=1):
            uid = cand["uid"]
            cota = cand.get("reference_code") or cand.get("cota")
            ano = cand.get("ano") or "s/d"
            desc = cand.get("description") or ""

            print("-" * 70)
            print(f"Item {idx_c}/{len(itens_a_julgar)} | Cota: {cota} | Ano: {ano}")
            print(f"Resumo: {desc[:400]}")
            if len(desc) > 400:
                print("...")

            t0 = time.time()
            while True:
                resp = input("Nota [0, 1, 2, q=sair]: ").strip().lower()
                if resp in ("0", "1", "2"):
                    delta_t = round(time.time() - t0, 2)
                    julg_q["julgamentos"][uid] = {
                        "nota": int(resp),
                        "delta_seconds": delta_t,
                        "timestamp": datetime.now().isoformat(),
                    }
                    salvar_julgamentos(julgamentos_salvos, caminho_saida)
                    break
                elif resp == "q":
                    print("\nSessão de julgamento salva. Até breve!")
                    return
                else:
                    print("Entrada inválida. Digite 0, 1, 2 ou q.")

    print("\nParabéns! Todas as consultas do pool foram julgadas.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Auditoria cega de consultas ")
    parser.add_argument("--gerar-pool", action="store_true", help="Gera o pool de candidatos")
    parser.add_argument("--pool", type=Path, default=ARQUIVO_POOL)
    parser.add_argument("--saida", type=Path, default=ARQUIVO_JULGAMENTOS)
    args = parser.parse_args()

    consultas = carregar_consultas()
    julgamentos = carregar_julgamentos_existentes(args.saida)

    if args.gerar_pool or not args.pool.is_file():
        print("Gerando pool de candidatos...")
        from ahu.dados import carregar

        pool = construir_pool_candidatos(carregar(), consultas)
        with open(args.pool, "w", encoding="utf-8") as f:
            json.dump(pool, f, indent=2, ensure_ascii=False)
        print(f"Pool salvo em {args.pool} com {len(pool)} consultas.")
    else:
        with open(args.pool, "r", encoding="utf-8") as f:
            pool = json.load(f)

    executar_julgamento_cli(pool, julgamentos, args.saida)


if __name__ == "__main__":
    main()
