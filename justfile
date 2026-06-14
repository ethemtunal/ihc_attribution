default:
    @just --list

# ── Code quality ───────────────────────────────────────────────────────────────

format:
    ruff check --select I --fix ./
    ruff format ./

fix:
    just format
    ruff check --fix

check:
    just fix
    mypy .
