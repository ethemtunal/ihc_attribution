default:
    @just --list

format:
    ruff check --select I --fix ./
    ruff format ./

fix:
    just format
    ruff check --fix

check:
    just fix
    mypy .
