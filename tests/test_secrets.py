"""Unit tests for cloud secret managers resolution."""

import base64
import sys
from unittest.mock import MagicMock, patch

import pytest

from speech_engine.config import Settings
from speech_engine.core.exceptions import ConfigurationError
from speech_engine.core.secrets import apply_secret_overrides


def test_secrets_backend_none_is_noop():
    settings = Settings(SECRETS_BACKEND="none", OPENAI_API_KEY="original")
    apply_secret_overrides(settings)
    assert settings.OPENAI_API_KEY == "original"


def test_aws_secrets_fetch(monkeypatch):
    settings = Settings(
        SECRETS_BACKEND="aws",
        AWS_REGION="us-east-1",
        SECRETS_PREFIX="speech-bridge/",
    )

    mock_boto3 = MagicMock()
    mock_client = MagicMock()
    mock_boto3.client.return_value = mock_client

    from botocore.exceptions import ClientError

    def get_secret(SecretId):
        if SecretId == "speech-bridge/OPENAI_API_KEY":
            return {"SecretString": "sk-aws-mock-key"}
        if SecretId == "speech-bridge/API_KEYS":
            return {"SecretString": "key1, key2"}
        raise ClientError(
            {"Error": {"Code": "ResourceNotFoundException"}}, "GetSecretValue"
        )

    mock_client.get_secret_value.side_effect = get_secret

    monkeypatch.setitem(sys.modules, "boto3", mock_boto3)

    apply_secret_overrides(settings)
    assert settings.OPENAI_API_KEY == "sk-aws-mock-key"
    assert settings.API_KEYS == ["key1", "key2"]


def test_aws_secrets_missing_boto3(monkeypatch):
    settings = Settings(SECRETS_BACKEND="aws")
    with patch.dict(sys.modules, {"boto3": None}):
        with pytest.raises(ConfigurationError) as exc:
            apply_secret_overrides(settings)
        assert "requires the 'boto3' package" in str(exc.value)


def test_gcp_secrets_missing_prefix(monkeypatch):
    monkeypatch.setitem(sys.modules, "google.cloud.secretmanager", MagicMock())
    monkeypatch.setitem(sys.modules, "google.api_core.exceptions", MagicMock())
    monkeypatch.setitem(sys.modules, "google.cloud", MagicMock())
    settings = Settings(SECRETS_BACKEND="gcp", SECRETS_PREFIX="")
    with pytest.raises(ConfigurationError) as exc:
        apply_secret_overrides(settings)
    assert "requires SECRETS_PREFIX='projects/<project-id>'" in str(exc.value)


def test_gcp_secrets_fetch(monkeypatch):
    settings = Settings(
        SECRETS_BACKEND="gcp",
        SECRETS_PREFIX="projects/my-proj",
    )

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.payload.data = b"sk-gcp-mock-key"
    mock_client.access_secret_version.return_value = mock_response

    mock_sm_mod = MagicMock()
    mock_sm_mod.SecretManagerServiceClient.return_value = mock_client

    monkeypatch.setitem(
        sys.modules,
        "google.api_core.exceptions",
        MagicMock(NotFound=Exception, PermissionDenied=Exception),
    )
    monkeypatch.setitem(sys.modules, "google.cloud.secretmanager", mock_sm_mod)
    monkeypatch.setitem(
        sys.modules, "google.cloud", MagicMock(secretmanager=mock_sm_mod)
    )

    apply_secret_overrides(settings)
    assert settings.OPENAI_API_KEY == "sk-gcp-mock-key"


def test_azure_secrets_fetch(monkeypatch):
    settings = Settings(
        SECRETS_BACKEND="azure",
        SECRETS_PREFIX="https://myvault.vault.azure.net",
    )

    mock_secret_client = MagicMock()
    mock_secret = MagicMock()
    mock_secret.value = "azure-key-secret"
    mock_secret_client.get_secret.return_value = mock_secret

    mock_az_sec = MagicMock()
    mock_az_sec.SecretClient.return_value = mock_secret_client

    monkeypatch.setitem(
        sys.modules, "azure.core.exceptions", MagicMock(ResourceNotFoundError=Exception)
    )
    monkeypatch.setitem(sys.modules, "azure.keyvault.secrets", mock_az_sec)
    monkeypatch.setitem(sys.modules, "azure.identity", MagicMock())

    apply_secret_overrides(settings)
    assert settings.AZURE_SPEECH_KEY == "azure-key-secret"


def test_azure_secrets_missing_prefix(monkeypatch):
    monkeypatch.setitem(
        sys.modules, "azure.core.exceptions", MagicMock(ResourceNotFoundError=Exception)
    )
    monkeypatch.setitem(sys.modules, "azure.keyvault.secrets", MagicMock())
    monkeypatch.setitem(sys.modules, "azure.identity", MagicMock())

    settings = Settings(SECRETS_BACKEND="azure", SECRETS_PREFIX="")
    with pytest.raises(ConfigurationError) as exc:
        apply_secret_overrides(settings)
    assert "requires SECRETS_PREFIX=<Key Vault URL>" in str(exc.value)


def test_oci_secrets_missing_prefix(monkeypatch):
    monkeypatch.setitem(sys.modules, "oci", MagicMock())
    monkeypatch.setitem(sys.modules, "oci.secrets", MagicMock())

    settings = Settings(SECRETS_BACKEND="oci", SECRETS_PREFIX="")
    with pytest.raises(ConfigurationError) as exc:
        apply_secret_overrides(settings)
    assert "requires SECRETS_PREFIX=<Vault OCID>" in str(exc.value)


def test_oci_secrets_fetch(monkeypatch):
    settings = Settings(
        SECRETS_BACKEND="oci",
        SECRETS_PREFIX="ocid1.vault.oc1..xyz",
    )

    encoded = base64.b64encode(b"sk-oci-secret").decode("utf-8")
    mock_bundle = MagicMock()
    mock_bundle.secret_bundle_content.content = encoded

    mock_data = MagicMock(data=mock_bundle)
    mock_secrets_client = MagicMock()
    mock_secrets_client.get_secret_bundle_by_name.return_value = mock_data

    mock_oci = MagicMock()
    mock_oci.secrets.SecretsClient.return_value = mock_secrets_client

    monkeypatch.setitem(sys.modules, "oci", mock_oci)
    monkeypatch.setitem(sys.modules, "oci.secrets", mock_oci.secrets)

    apply_secret_overrides(settings)
    assert settings.OPENAI_API_KEY == "sk-oci-secret"
