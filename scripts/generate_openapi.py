import pathlib

import yaml

from src.api.main import app  # шлях до модуля, де є `app = create_app()`

OUTPUT = pathlib.Path("docs/api/openapi-generated.yaml")


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    spec = app.openapi()
    OUTPUT.write_text(
        yaml.safe_dump(spec, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"Wrote {OUTPUT} ({len(spec['paths'])} paths)")


if __name__ == "__main__":
    main()