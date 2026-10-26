"""Створює файл ``.env`` з випадковим паролем локальної бази.

Запуск з кореня репозиторію (працює на macOS, Linux і Windows):

    python scripts/create_env.py           # якщо .env ще немає
    python scripts/create_env.py --force   # перезаписати наявний

Файл містить пароль для Docker Compose і дві адреси: робочої бази
(``DATABASE_URL``) та тестової (``TEST_DATABASE_URL``). Він у
``.gitignore`` — не комітьте його.
"""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
BASE_URL = "postgresql://notely:{password}@localhost:5432/{database}"


def render_env(password: str) -> str:
    """Вміст ``.env`` для заданого пароля."""
    work_url = BASE_URL.format(password=password, database="notely")
    test_url = BASE_URL.format(password=password, database="notely_test")
    return (
        f"POSTGRES_PASSWORD={password}\n"
        f"DATABASE_URL={work_url}\n"
        f"TEST_DATABASE_URL={test_url}\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--force", action="store_true", help="перезаписати наявний .env"
    )
    args = parser.parse_args(argv)

    if ENV_FILE.exists() and not args.force:
        print(
            f"{ENV_FILE.name} уже існує. Щоб створити новий пароль, "
            "запустіть з --force і перестворіть базу: "
            "docker compose down -v && docker compose up -d",
            file=sys.stderr,
        )
        return 1

    ENV_FILE.write_text(render_env(secrets.token_hex(16)), encoding="utf-8")
    print(f"Створено {ENV_FILE}.")
    print(
        "Якщо база вже була створена зі старим паролем, перестворіть її: "
        "docker compose down -v && docker compose up -d"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())


# File was created by Claude. Reviewed by Kozynska Anastasia
