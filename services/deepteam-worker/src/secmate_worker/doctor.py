from .runtime_policy import (
    configure_runtime_environment,
    validate_installed_frameworks,
    validate_runtime,
)


def main() -> None:
    configure_runtime_environment()
    validate_runtime()
    validate_installed_frameworks()
    print("SecMate DeepTeam worker runtime policy: PASS")


if __name__ == "__main__":
    main()
