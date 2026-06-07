default:
    @just --list

# ── Airflow ────────────────────────────────────────────────────────────────────

airflow-start:
    docker compose up -d

airflow-stop:
    docker compose down

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
