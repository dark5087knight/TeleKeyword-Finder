"""Generate a secure Fernet master key for encrypting user secrets at rest."""

from cryptography.fernet import Fernet


def main() -> None:
    key = Fernet.generate_key().decode()
    print("Generated Fernet master key:")
    print(key)
    print("\nAdd this to your .env file as:")
    print(f"SECRETS_MASTER_KEY={key}")


if __name__ == "__main__":
    main()
