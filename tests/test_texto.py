"""Testes de `ahu/texto.py`: a normalização que o léxico e a consulta compartilham."""
from ahu import texto


def test_normalizar_busca_tira_acento_caixa_e_pontuacao():
    assert texto.normalizar_busca("D. José de Mello-Castro!") == "d jose de mello castro"
    assert texto.normalizar_busca("") == ""
    assert texto.normalizar_busca(None) == ""


def test_fonetica_neutraliza_grafia_antiga():
    assert texto.fonetica("paes") == texto.fonetica("pais")
    assert texto.fonetica("joze") == texto.fonetica("jose")
    assert texto.fonetica("mello") == texto.fonetica("melo")
    assert texto.fonetica("xassim") == texto.fonetica("chassim")


def test_tokenizar_tira_palavras_vazias_e_aplica_a_fonetica():
    assert texto.tokenizar("Carta do Marquês do Lavradio") == ["carta", "marques", "lavradio"]
    assert texto.tokenizar("obras do porto", stopwords=False) == ["obras", "do", "porto"]
    assert texto.tokenizar("Mello", foneticamente=False) == ["mello"]
