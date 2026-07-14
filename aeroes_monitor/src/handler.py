"""Entrypoint AWS Lambda: SSM (segredos) e DynamoDB (estado) em volta de run_scan.

Fluxo por invocação: segredos do SSM (cache no cold start) → GetItem do
state.json no DynamoDB para /tmp → mesmo run_scan do modo local → PutItem do
estado. Debug de falha vai ao CloudWatch (run_scan loga o HTML), não mais S3.

Semântica de erro: falha de varredura TRATADA retorna {"ok": false} sem
exceção (o app já avisou no Discord na transição). Exceção NÃO tratada
(SSM/DDB negados, bug) propaga de propósito — vira métrica Errors e dispara o
alarme, cobrindo exatamente o buraco em que o Discord não pôde ser avisado.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3

from config import load_config
from main import run_scan, setup_logging

# Logs em BRT no Lambda (Linux). TZ é chave reservada nas env vars da função,
# então setamos aqui; no-op no Windows local (sem time.tzset).
if hasattr(time, "tzset"):
    os.environ.setdefault("TZ", "America/Sao_Paulo")
    time.tzset()

logger = logging.getLogger(__name__)

STATE_PATH = Path("/tmp/state.json")
STATE_ID = "state"
SECRET_NAMES = ("saga-username", "saga-password", "discord-webhook-url")

_ssm_client = None
_ddb_client = None
_secrets_cache: dict[str, str] | None = None


def _ssm():
    global _ssm_client
    if _ssm_client is None:
        _ssm_client = boto3.client("ssm")
    return _ssm_client


def _ddb():
    global _ddb_client
    if _ddb_client is None:
        _ddb_client = boto3.client("dynamodb")
    return _ddb_client


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


def _load_state(table: str) -> None:
    """GetItem → /tmp/state.json. Item ausente = baseline (como no modo local).

    ConsistentRead: nunca diffar contra réplica atrasada. Remove cópia local
    obsoleta de invocação anterior (warm start) quando não há item.
    """
    resp = _ddb().get_item(
        TableName=table, Key={"id": {"S": STATE_ID}}, ConsistentRead=True
    )
    item = resp.get("Item")
    if item and "payload" in item:
        STATE_PATH.write_text(item["payload"]["S"], encoding="utf-8")
    else:
        STATE_PATH.unlink(missing_ok=True)


def _save_state(table: str) -> None:
    """PutItem sempre que o arquivo existir (item único, escrita atômica)."""
    if STATE_PATH.exists():
        _ddb().put_item(
            TableName=table,
            Item={
                "id": {"S": STATE_ID},
                "payload": {"S": STATE_PATH.read_text(encoding="utf-8")},
                "updated_at": {"S": datetime.now(timezone.utc).isoformat()},
            },
        )


def lambda_handler(event, context) -> dict:
    table = os.environ["STATE_TABLE"]
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
    _load_state(table)
    ok = run_scan(config, STATE_PATH)
    _save_state(table)
    return {"ok": ok}
