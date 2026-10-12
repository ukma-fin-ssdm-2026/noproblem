from src.api.main import OPENAPI_PATH, app, export_openapi


def main() -> None:
    if not export_openapi(app):
        raise OSError(f"Could not write OpenAPI specification to {OPENAPI_PATH}")
    print(f"Wrote {OPENAPI_PATH} ({len(app.openapi()['paths'])} paths)")


if __name__ == "__main__":
    main()
