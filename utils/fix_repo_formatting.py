#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Varre o repositório e:
  1) Converte CRLF/CR -> LF.
  2) Garante newline no final do arquivo.
  3) Normaliza shebang de scripts Python p/ '#!/usr/bin/env python3'.
  4) Torna executáveis arquivos .py, .launch, .launch.py, .sh e arquivos com shebang.
  5) Pule diretórios irrelevantes (ex.: .git, build, install, log, __pycache__).

Uso:
  python3 fix_repo_formatting.py [--root <dir>] [--dry-run] [--verbose]

Dicas:
  - Rode a partir da raiz do repositório.
  - Use --dry-run para ver o que seria feito sem alterar nada.
"""

import argparse
import os
import stat
from typing import Tuple, List

# Pastas a ignorar durante o walk
SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    "build",
    "install",
    "log",
    "logs",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "node_modules",
    ".venv",
    "venv",
    ".idea",
    ".vscode",
    ".DS_Store",
}

# Extensões candidatas a normalização e permissões
TEXT_EXTS = {
    ".py",
    ".launch",
    ".launch.py",
    ".xml",
    ".xacro",
    ".urdf",
    ".sdf",
    ".world",
    ".cfg",
    ".ini",
    ".toml",
    ".yaml",
    ".yml",
    ".sh",
    ".bash",
    ".zsh",
    ".txt",
    ".md",
    ".rst",
    ".sv",
    ".proto",
    ".hpp",
    ".h",
    ".hh",
    ".c",
    ".cc",
    ".cpp",
    ".cu",
    ".java",
    ".gradle",
    ".properties",
    ".csv",
    ".tsv",
    ".json",
    ".srv",
    ".msg",
    ".action",
    ".idl",
    ".py.in",
    ".cmake",
    "CMakeLists.txt",
    "Makefile",
    "Dockerfile",
}

# Extensões cuja permissão executável deve ser garantida
EXECUTABLE_EXTS = {
    ".py",
    ".launch",
    ".launch.py",
    ".sh",
    ".bash",
    ".zsh",
}

# Arquivos sem extensão mas com nomes típicos de script
EXECUTABLE_BASENAMES = {
    "entrypoint",
    "setup_env",
    "env.sh",
    "activate",
    "colcon",
    "ros_entrypoint.sh",
}

# Tamanho máximo para ler na detecção (evitar carregar arquivos enormes na RAM)
MAX_READ_FOR_DETECT = 1024 * 1024 * 5  # 5 MB


def looks_like_text(data: bytes) -> bool:
    """Heurística simples para detectar arquivo texto vs binário."""
    if b"\x00" in data:
        return False
    # Permite UTF-8 com alguns bytes acima de 0x7F; regra simples:
    # se muitos bytes são de controle estranhos, provavelmente binário.
    # Aqui aceitamos quase tudo sem NUL como texto.
    return True


def normalize_newlines(content: str) -> Tuple[str, bool]:
    """Converte CRLF/CR para LF e garante newline final."""
    changed = False

    # Normaliza finais de linha
    new = content.replace("\r\n", "\n").replace("\r", "\n")
    if new != content:
        changed = True

    # Garante newline no final
    if not new.endswith("\n"):
        new += "\n"
        changed = True

    return new, changed


def normalize_shebang(first_line: str) -> Tuple[str, bool]:
    """
    Se o shebang indicar Python, normaliza para '#!/usr/bin/env python3'.
    Retorna (linha_normalizada, alterou).
    """
    changed = False
    fl = first_line.strip()

    if fl.startswith("#!"):
        low = fl.lower()
        if "python" in low:
            # Alguns shebangs comuns em Windows/WSL ou ambientes específicos
            desired = "#!/usr/bin/env python3"
            if fl != desired:
                return desired + "\n", True
    return first_line, changed


def should_set_executable(path: str, first_line: str) -> bool:
    """Decide se o arquivo deve ser executável."""
    base = os.path.basename(path)
    _, ext = os.path.splitext(path)

    # Shebang manda
    if first_line.startswith("#!"):
        return True

    # Extensões
    if ext in EXECUTABLE_EXTS:
        return True

    # Alguns nomes típicos
    if base in EXECUTABLE_BASENAMES:
        return True

    return False


def in_skipped_dir(root: str, name: str) -> bool:
    if name in SKIP_DIRS:
        return True
    # Ignora diretórios iniciados por . e não listados explicitamente, exceto .github (útil)
    if name.startswith(".") and name not in {".github"} and name not in SKIP_DIRS:
        return True
    return False


def process_file(path: str, dry_run: bool = False, verbose: bool = False) -> Tuple[bool, bool, bool]:
    """
    Processa um arquivo:
      - Normaliza EOL
      - Corrige shebang (se Python)
      - Ajusta permissão executável
    Retorna (alterou_conteudo, alterou_permissao, pulado_por_binario_ou_grande)
    """
    # Ignora arquivos muito grandes para segurança
    try:
        size = os.path.getsize(path)
    except OSError:
        return False, False, False

    if size > MAX_READ_FOR_DETECT:
        # Só tenta ajustar permissão por extensão/shebang sem carregar conteúdo
        content = b""
    else:
        try:
            with open(path, "rb") as f:
                content = f.read()
        except Exception:
            return False, False, False

    # Detecta binário
    if content and not looks_like_text(content):
        return (False, False, True)

    text_changed = False
    shebang_changed = False
    first_line = ""
    new_text = None

    if content:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            # Tenta latin-1 como fallback para não travar (iremos regravar em UTF-8)
            text = content.decode("latin-1")

        lines = text.splitlines(keepends=True)
        if lines:
            first_line = lines[0]
            # Normaliza shebang de python
            fixed_first, shebang_changed = normalize_shebang(first_line)
            if shebang_changed:
                lines[0] = fixed_first

        # Normaliza finais de linha + newline final
        text2 = "".join(lines)
        normalized, nl_changed = normalize_newlines(text2)

        text_changed = shebang_changed or nl_changed
        if text_changed:
            new_text = normalized

    # Decide se precisa ser executável
    exec_needed = should_set_executable(path, first_line or "")

    # Define se vamos alterar permissão
    perm_changed = False
    try:
        st = os.stat(path)
        mode = st.st_mode
        if exec_needed:
            new_mode = mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        else:
            new_mode = mode
        if new_mode != mode:
            perm_changed = True
    except OSError:
        new_mode = None

    # Aplica alterações
    if dry_run:
        if verbose and (text_changed or perm_changed):
            print(f"[DRY-RUN] {path} :: text_changed={text_changed}, perm_changed={perm_changed}")
        return text_changed, perm_changed, False

    try:
        if text_changed and new_text is not None:
            # Regrava sempre em UTF-8 com LF
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(new_text)

        if perm_changed and new_mode is not None:
            os.chmod(path, new_mode)

    except Exception as e:
        print(f"[ERRO] Falha ao processar {path}: {e}")

    return text_changed, perm_changed, False


def is_candidate_file(path: str) -> bool:
    """Retorna True se o arquivo parece texto e/ou está em nossa lista alvo."""
    base = os.path.basename(path)
    name, ext = os.path.splitext(path)

    # Arquivos sem extensão mas importantes
    if os.path.basename(path) in EXECUTABLE_BASENAMES:
        return True

    # CMakeLists.txt e Makefile entram mesmo sem extensão
    if base in {"CMakeLists.txt", "Makefile"}:
        return True

    # Dockerfile (com ou sem extensão)
    if os.path.basename(path).lower().startswith("dockerfile"):
        return True

    # Extensões conhecidas
    if ext in TEXT_EXTS:
        return True

    # .launch.py às vezes aparece como ".launch.py" (dupla extensão)
    if path.endswith(".launch.py"):
        return True

    return False


def walk_and_fix(root: str, dry_run: bool = False, verbose: bool = False) -> Tuple[int, int, int, int]:
    changed_files = 0
    changed_perms = 0
    skipped_bin_or_large = 0
    visited = 0

    for cur, dirs, files in os.walk(root):
        # filtra dirs
        dirs[:] = [d for d in dirs if not in_skipped_dir(cur, d)]

        for fname in files:
            path = os.path.join(cur, fname)

            # pular links simbólicos
            if os.path.islink(path):
                continue

            if not is_candidate_file(path):
                continue

            visited += 1
            t_changed, p_changed, skipped = process_file(path, dry_run=dry_run, verbose=verbose)

            if skipped:
                skipped_bin_or_large += 1
                continue
            if t_changed:
                changed_files += 1
            if p_changed:
                changed_perms += 1

    return visited, changed_files, changed_perms, skipped_bin_or_large


def main():
    parser = argparse.ArgumentParser(description="Normaliza EOL, corrige shebang e permissões executáveis no repositório.")
    parser.add_argument("--root", default=".", help="Diretório raiz para varrer (default: .)")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o que seria alterado sem escrever nada.")
    parser.add_argument("--verbose", action="store_true", help="Saída detalhada.")
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    print(f"[INFO] Raiz: {root}")
    visited, changed_files, changed_perms, skipped = walk_and_fix(root, dry_run=args.dry_run, verbose=args.verbose)

    print("\n[RESUMO]")
    print(f"Arquivos candidatos visitados : {visited}")
    print(f"Arquivos com conteúdo alterado: {changed_files}")
    print(f"Arquivos com permissão +x     : {changed_perms}")
    print(f"Pulados (binários/grandes)    : {skipped}")
    if args.dry_run:
        print("\n[INFO] DRY-RUN: Nenhuma alteração foi gravada.")
    else:
        print("\n[OK] Concluído.")


if __name__ == "__main__":
    main()
