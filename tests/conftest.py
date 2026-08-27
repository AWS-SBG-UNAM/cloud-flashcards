"""Fixtures compartidas.

Las dos Lambdas definen un modulo llamado `app`, asi que no pueden importarse
por nombre sin colisionar. Se cargan desde su ruta con un alias distinto.
"""

import importlib.util
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TABLE_NAME = "flashcards-test"
BUCKET_NAME = "decks-test"


def _load(alias: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(alias, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def aws_env(monkeypatch):
    """Credenciales ficticias: evita que moto toque una cuenta real."""
    for key, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": "us-east-1",
        "TABLE_NAME": TABLE_NAME,
    }.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def parser_app():
    """Modulo del parser, con sus clientes cacheados reiniciados.

    Ambas Lambdas memorizan el cliente en una global (patron de reutilizacion
    entre invocaciones). Sin este reset, un test heredaria el cliente creado
    dentro del mock de otro test.
    """
    module = _load("parser_app", "backend/parser/app.py")
    module._s3_client = None
    module._table = None
    return module


@pytest.fixture
def api_app():
    module = _load("api_app", "backend/api/app.py")
    module._table = None
    return module


@pytest.fixture
def aws(aws_env):
    """Activa moto durante todo el test.

    Tiene que ser un fixture y no el decorador `@mock_aws`: pytest resuelve
    los fixtures ANTES de entrar en el cuerpo del test, asi que con el
    decorador los clientes se crearian fuera del mock y saldrian a la red.
    """
    from moto import mock_aws

    with mock_aws():
        yield


@pytest.fixture
def dynamodb_table(aws):
    import boto3

    resource = boto3.resource("dynamodb", region_name="us-east-1")
    resource.create_table(
        TableName=TABLE_NAME,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": "deckId", "AttributeType": "S"},
            {"AttributeName": "questionId", "AttributeType": "S"},
            {"AttributeName": "entity", "AttributeType": "S"},
            {"AttributeName": "catalogSort", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "deckId", "KeyType": "HASH"},
            {"AttributeName": "questionId", "KeyType": "RANGE"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "DecksIndex",
                "KeySchema": [
                    {"AttributeName": "entity", "KeyType": "HASH"},
                    {"AttributeName": "catalogSort", "KeyType": "RANGE"},
                ],
                "Projection": {
                    "ProjectionType": "INCLUDE",
                    "NonKeyAttributes": [
                        "deckTitle",
                        "category",
                        "questionCount",
                        "updatedAt",
                    ],
                },
            }
        ],
    )
    return resource.Table(TABLE_NAME)


@pytest.fixture
def s3_bucket(aws):
    import boto3

    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket=BUCKET_NAME)
    return client


def s3_event(bucket: str, key: str) -> dict:
    """Evento de S3 reducido a los campos que consume el handler."""
    return {
        "Records": [
            {"s3": {"bucket": {"name": bucket}, "object": {"key": key}}}
        ]
    }
