"""Entrypoint AWS Lambda: SSM (segredos) e S3 (estado) ao redor de run_scan.

Fluxo por invocação (spec 2026-07-12): segredos do SSM (cache de módulo no
cold start) → GET state.json do S3 para /tmp → mesmo run_scan do modo local
→ PUT do state de volta → em falha, sobe artefatos de debug para debug/.

Semântica de erro: falha de varredura TRATADA retorna {"ok": false} sem
exceção (o app já avisou no Discord na transição). Exceção NÃO tratada
(SSM negado, S3 fora, bug) propaga de propósito — vira métrica Errors e
dispara o alarme, cobrindo exatamente o buraco em que o Discord não pôde
ser avisado.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from config import load_config
from main import run_scan, setup_logging

logger = logging.getLogger(__name__)

STATE_PATH = Path("/tmp/state.json")
SECRET_NAMES = ("saga-username", "saga-password", "discord-webhook-url")

_ssm_client = None
_s3_client = None
_secrets_cache: dict[str, str] | None = None


def _ssm():
    global _ssm_client
    if _ssm_client is None:
        _ssm_client = boto3.client("ssm")
    return _ssm_client


def _s3():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3")
    return _s3_client


def _load_secrets() -> dict[str, str]:
    """3 SecureStrings do SSM; cache de módulo (1 leitura por cold start)."""
    global _secrets_cache
    if _secrets_cache is None:
        prefix = os.environ["SSM_PREFIX"].rstrip("/")
        _secrets_cache = {
            name: _ssm().get_parameter(
                Name=f"{prefix}/{name}", WithDecryption=True
            )["Parameter"]["Value"]
            for name in SECRET_NAMES
        }
    return _secrets_cache


def _download_state(bucket: str, key: str) -> None:
    """GET state.json → /tmp. Ausente = baseline (como no modo local).

    Remove cópia local obsoleta de invocação anterior (warm start); outros
    erros de S3 propagam (alarme).
    """
    try:
        _s3().download_file(bucket, key, str(STATE_PATH))
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code not in ("404", "NoSuchKey"):
            raise
        STATE_PATH.unlink(missing_ok=True)


def _upload_state(bucket: str, key: str) -> None:
    """PUT sempre que o arquivo existir (54 PUTs/dia custam nada)."""
    if STATE_PATH.exists():
        _s3().upload_file(str(STATE_PATH), bucket, key)


def _upload_debug_artifacts(bucket: str, prefix: str, debug_dir: Path) -> None:
    """Sobe e apaga artefatos locais (warm start não re-sobe os antigos).

    Melhor esforço: a varredura já falhou e o Discord já foi avisado;
    debug perdido não justifica derrubar o handler.
    """
    try:
        if not debug_dir.is_dir():
            return
        for artifact in sorted(debug_dir.iterdir()):
            if artifact.is_file():
                _s3().upload_file(str(artifact), bucket, f"{prefix}{artifact.name}")
                artifact.unlink()
                logger.info(
                    "Debug enviado: s3://%s/%s%s", bucket, prefix, artifact.name
                )
    except Exception:
        logger.exception("Falha ao subir artefatos de debug")


def lambda_handler(event, context) -> dict:
    bucket = os.environ["STATE_BUCKET"]
    key = os.environ.get("STATE_KEY", "state.json")
    secrets = _load_secrets()
    config = load_config(
        os.environ.get("CONFIG_FILE", "config.lambda.ini"),
        overrides={
            ("credentials", "username"): secrets["saga-username"],
            ("credentials", "password"): secrets["saga-password"],
            ("discord", "webhook_url"): secrets["discord-webhook-url"],
            ("logging", "level"): os.environ.get("LOG_LEVEL", "INFO"),
        },
    )
    setup_logging(config.logging)
    _download_state(bucket, key)
    ok = run_scan(config, STATE_PATH)
    _upload_state(bucket, key)
    if not ok:
        _upload_debug_artifacts(
            bucket,
            os.environ.get("DEBUG_PREFIX", "debug/"),
            Path(config.selenium.debug_dir),
        )
    return {"ok": ok}
