"""Estrutura do repositório e regras de convenção."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def test_estrutura_do_repositorio():
    pastas = ("ahu", "web", "build", "coleta", "avaliacao", "tests", "corpus", "app_dados", "scripts")
    for pasta in pastas:
        assert (RAIZ / pasta).is_dir(), pasta


def test_arquivos_de_convencao():
    for arq in ("AGENTS.md", "CLAUDE.md", "GEMINI.md", "LICENSE", "LICENSE-DATA.md", "README.md",
                "requirements.txt", "pyproject.toml", "CITATION.cff"):
        assert (RAIZ / arq).is_file(), arq
    assert "AGENTS.md" in (RAIZ / "CLAUDE.md").read_text(encoding="utf-8")
    assert "AGENTS.md" in (RAIZ / "GEMINI.md").read_text(encoding="utf-8")


def test_python_311_declarado():
    assert 'requires-python = ">=3.11"' in (RAIZ / "pyproject.toml").read_text(encoding="utf-8")
    assert "FROM python:3.11" in (RAIZ / "Dockerfile").read_text(encoding="utf-8")


def test_dependencias_fixadas_sem_openai():
    texto = (RAIZ / "requirements.txt").read_text(encoding="utf-8")
    # Comentário e opção do pip (`--extra-index-url`) não são dependência.
    linhas = [ln.strip() for ln in texto.splitlines()
              if ln.strip() and not ln.lstrip().startswith(("#", "-"))]
    assert linhas
    assert all("==" in ln for ln in linhas)
    assert not any(ln.lower().startswith("openai") for ln in linhas)


def test_a_execucao_nao_depende_de_torch():
    """O `requirements.txt` é o que a imagem do app instala, e ele não tem torch."""
    runtime = (RAIZ / "requirements.txt").read_text(encoding="utf-8")
    pacotes = [ln.split("==")[0].strip().lower() for ln in runtime.splitlines()
               if ln.strip() and not ln.lstrip().startswith(("#", "-"))]
    assert "torch" not in pacotes and "sentence-transformers" not in pacotes, pacotes
    assert "onnxruntime" in pacotes and "tokenizers" in pacotes


def test_o_torch_da_construcao_e_so_cpu():
    """Ele sobrevive só no requirements-build.txt, e lá continua sendo o só-CPU: o do PyPI em
    Linux arrasta as bibliotecas CUDA, que a construção também não usa."""
    arquivo = RAIZ / "requirements-build.txt"
    assert arquivo.is_file()
    texto = arquivo.read_text(encoding="utf-8")
    assert "-r requirements.txt" in texto
    assert "--extra-index-url https://download.pytorch.org/whl/cpu" in texto
    assert "torch==2.8.0+cpu" in texto
    assert "sentence-transformers==5.2.3" in texto


