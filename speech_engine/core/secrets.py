"""Optional cloud secret-manager resolution.

When ``SECRETS_BACKEND`` is set to ``aws``/``azure``/``gcp``/``oci``, the
credential-bearing settings are fetched from the corresponding managed
secret store at startup and applied to the process-wide ``Settings``
instance, replacing any plaintext env values. When it is ``none`` (the
default) nothing happens and env/`.env`/`config.yaml` values are used.

Convention: one secret per setting, named after the setting field
(``OPENAI_API_KEY``, ``AZURE_SPEECH_KEY``, ``API_KEYS`` …). Missing
secrets are skipped so you only need to store the ones you use.

All provider SDKs are imported lazily so a deployment installs only the
backend it actually uses. Adapters follow the same lazy-import pattern as
the STT/TTS remote engines.
"""

import logging

from speech_engine.config import Settings
from speech_engine.core.exceptions import ConfigurationError

logger = logging.getLogger(__name__)

# Settings fields that may live in a secret store. Only these are fetched.
SECRET_FIELDS: list[str] = [
    "OPENAI_API_KEY",
    "AZURE_SPEECH_KEY",
    "AZURE_SPEECH_REGION",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "API_KEYS",
]

# Fields whose value is a list; a fetched string is split on commas.
_LIST_FIELDS = {"API_KEYS"}


def apply_secret_overrides(settings: Settings) -> None:
    """Fetch configured secrets and mutate ``settings`` in place.

    No-op when ``SECRETS_BACKEND == "none"``. Raises ConfigurationError on
    misconfiguration or SDK/transport failure so startup fails fast.
    """
    backend = settings.SECRETS_BACKEND
    if backend == "none":
        return

    fetchers = {
        "aws": _fetch_aws,
        "gcp": _fetch_gcp,
        "azure": _fetch_azure,
        "oci": _fetch_oci,
    }
    fetcher = fetchers.get(backend)
    if fetcher is None:  # pragma: no cover - guarded by the Literal type
        raise ConfigurationError(f"Unknown SECRETS_BACKEND '{backend}'.")

    logger.info("Resolving secrets from %s secret manager", backend)
    resolved = fetcher(settings)

    applied = []
    for field, value in resolved.items():
        if value is None or value == "":
            continue
        if field in _LIST_FIELDS and isinstance(value, str):
            value = [item.strip() for item in value.split(",") if item.strip()]
        setattr(settings, field, value)
        applied.append(field)
    logger.info("Applied %d secret(s) from %s: %s", len(applied), backend, applied)


def _fetch_aws(settings: Settings) -> dict[str, object]:
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError as exc:
        raise ConfigurationError(
            "SECRETS_BACKEND=aws requires the 'boto3' package."
        ) from exc

    client = boto3.client("secretsmanager", region_name=settings.AWS_REGION)
    prefix = settings.SECRETS_PREFIX
    out: dict[str, object] = {}
    for field in SECRET_FIELDS:
        secret_id = f"{prefix}{field}"
        try:
            response = client.get_secret_value(SecretId=secret_id)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"ResourceNotFoundException", "AccessDeniedException"}:
                continue  # secret not stored / not permitted — skip
            raise ConfigurationError(
                f"AWS Secrets Manager error for '{secret_id}': {exc}"
            ) from exc
        out[field] = response.get("SecretString")
    return out


def _fetch_gcp(settings: Settings) -> dict[str, object]:
    try:
        from google.api_core.exceptions import NotFound, PermissionDenied
        from google.cloud import secretmanager
    except ImportError as exc:
        raise ConfigurationError(
            "SECRETS_BACKEND=gcp requires 'google-cloud-secret-manager'."
        ) from exc

    project = settings.SECRETS_PREFIX  # e.g. "projects/my-project"
    if not project:
        raise ConfigurationError(
            "SECRETS_BACKEND=gcp requires SECRETS_PREFIX='projects/<project-id>'."
        )
    client = secretmanager.SecretManagerServiceClient()
    out: dict[str, object] = {}
    for field in SECRET_FIELDS:
        name = f"{project}/secrets/{field}/versions/latest"
        try:
            response = client.access_secret_version(name=name)
        except (NotFound, PermissionDenied):
            continue
        except Exception as exc:  # noqa: BLE001 - surfaced as config error
            raise ConfigurationError(
                f"GCP Secret Manager error for '{name}': {exc}"
            ) from exc
        out[field] = response.payload.data.decode("utf-8")
    return out


def _fetch_azure(settings: Settings) -> dict[str, object]:
    try:
        from azure.core.exceptions import ResourceNotFoundError
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient
    except ImportError as exc:
        raise ConfigurationError(
            "SECRETS_BACKEND=azure requires 'azure-keyvault-secrets' and "
            "'azure-identity'."
        ) from exc

    vault_url = settings.SECRETS_PREFIX
    if not vault_url:
        raise ConfigurationError(
            "SECRETS_BACKEND=azure requires SECRETS_PREFIX=<Key Vault URL>."
        )
    client = SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())
    out: dict[str, object] = {}
    for field in SECRET_FIELDS:
        # Key Vault secret names cannot contain underscores.
        name = field.replace("_", "-")
        try:
            secret = client.get_secret(name)
        except ResourceNotFoundError:
            continue
        except Exception as exc:  # noqa: BLE001
            raise ConfigurationError(
                f"Azure Key Vault error for '{name}': {exc}"
            ) from exc
        out[field] = secret.value
    return out


def _fetch_oci(settings: Settings) -> dict[str, object]:
    try:
        import base64

        import oci
    except ImportError as exc:
        raise ConfigurationError(
            "SECRETS_BACKEND=oci requires the 'oci' package."
        ) from exc

    vault_id = settings.SECRETS_PREFIX
    if not vault_id:
        raise ConfigurationError(
            "SECRETS_BACKEND=oci requires SECRETS_PREFIX=<Vault OCID>."
        )
    config = oci.config.from_file()  # standard ~/.oci/config resolution
    client = oci.secrets.SecretsClient(config)
    out: dict[str, object] = {}
    for field in SECRET_FIELDS:
        name = field.replace("_", "-")
        try:
            bundle = client.get_secret_bundle_by_name(
                secret_name=name, vault_id=vault_id
            ).data
        except oci.exceptions.ServiceError as exc:
            if exc.status in (400, 404):
                continue
            raise ConfigurationError(f"OCI Vault error for '{name}': {exc}") from exc
        content = bundle.secret_bundle_content.content
        out[field] = base64.b64decode(content).decode("utf-8")
    return out
