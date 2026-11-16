import json

from .deepteam_catalog import catalog_payload


def main() -> None:
    print(json.dumps(catalog_payload()))


if __name__ == "__main__":
    main()
