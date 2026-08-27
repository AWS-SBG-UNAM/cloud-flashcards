"""API de consulta de mazos.

Rutas (API Gateway REST, integracion proxy):

    GET /decks            catalogo de mazos, agrupable por tematica
    GET /decks/{deckId}   preguntas de un mazo concreto

El catalogo sale de un Query sobre el indice disperso `DecksIndex`, no de un
Scan: solo los items "#META" llevan el atributo `entity`, asi que el indice
contiene una fila por mazo y ninguna pregunta.

CORS
----
Con un REST API la funcion SI tiene que emitir `Access-Control-Allow-Origin`.
La propiedad `Cors` de `AWS::Serverless::Api` solo cubre el preflight: genera
el metodo OPTIONS con una integracion mock. La respuesta real del GET sale de
aqui y el gateway no la toca, asi que sin esta cabecera el navegador bloquea
la lectura.

Es exactamente lo contrario a un HTTP API (v2), que inyecta las cabeceras en
todas las respuestas y donde anadirlas aqui provocaria un valor duplicado.
El evento tambien difiere: REST usa payload v1.0, no v2.0.
"""

from __future__ import annotations

import json
import logging
import os
from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

LOGGER = logging.getLogger()
LOGGER.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# Topes de seguridad: evitan que una coleccion grande agote memoria o timeout.
MAX_QUESTIONS = 500
MAX_DECKS = 200

DECKS_INDEX = "DecksIndex"
DECK_SORT_KEY = "#META"
CATALOG_PARTITION = "DECK"

# Debe coincidir con el parametro CorsAllowOrigin de la plantilla.
CORS_ALLOW_ORIGIN = os.environ.get("CORS_ALLOW_ORIGIN", "*")

_table = None


def _questions_table():
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
    return _table


class DecimalEncoder(json.JSONEncoder):
    """DynamoDB devuelve todos los numeros como `Decimal`, que `json` no sabe
    serializar. Se convierten a `int` cuando no tienen parte fraccionaria."""

    def default(self, o: Any) -> Any:
        if isinstance(o, Decimal):
            return int(o) if o % 1 == 0 else float(o)
        return super().default(o)


def _response(status: int, body: dict[str, Any], cache_seconds: int = 0) -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Access-Control-Allow-Origin": CORS_ALLOW_ORIGIN,
    }
    if cache_seconds:
        headers["Cache-Control"] = f"public, max-age={cache_seconds}"

    return {
        "statusCode": status,
        "headers": headers,
        "body": json.dumps(body, cls=DecimalEncoder, ensure_ascii=False),
    }


def _query_all(limit: int, **kwargs: Any) -> list[dict[str, Any]]:
    """Ejecuta un Query paginado hasta agotar resultados o alcanzar `limit`."""
    table = _questions_table()
    items: list[dict[str, Any]] = []

    while len(items) < limit:
        response = table.query(**kwargs)
        items.extend(response.get("Items", []))

        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key

    return items[:limit]


def fetch_catalog() -> list[dict[str, Any]]:
    """Devuelve un item por mazo con un unico Query sobre el indice disperso.

    Todos los mazos comparten la misma PK en el indice (`entity = "DECK"`), lo
    que los deja en una sola particion logica: leer el catalogo completo es una
    operacion, no un Scan. El sort key `catalogSort` ya viene formado como
    "categoria#titulo", asi que DynamoDB los devuelve ordenados.
    """
    items = _query_all(
        MAX_DECKS,
        IndexName=DECKS_INDEX,
        KeyConditionExpression=Key("entity").eq(CATALOG_PARTITION),
    )

    if len(items) == MAX_DECKS:
        LOGGER.warning("Catalogo truncado a %d mazos", MAX_DECKS)

    return items


def fetch_deck(deck_id: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Recupera un mazo entero con un unico Query paginado.

    Este es el motivo de que `deckId` sea la clave de particion: el item de
    mazo y todas sus preguntas viven juntos y se leen de una vez.

    Devuelve `(meta, preguntas)`. El item "#META" llega siempre primero por
    ordenacion del sort key, pero se filtra por clave y no por posicion.
    """
    items = _query_all(
        MAX_QUESTIONS + 1, KeyConditionExpression=Key("deckId").eq(deck_id)
    )

    meta = next((i for i in items if i.get("questionId") == DECK_SORT_KEY), None)
    questions = [i for i in items if i.get("questionId") != DECK_SORT_KEY]

    # El orden de DynamoDB es el del sort key (uuid), es decir arbitrario.
    # `position` conserva el orden original del archivo Markdown.
    questions.sort(key=lambda item: item.get("position", 0))
    return meta, questions


def serialize_deck(item: dict[str, Any]) -> dict[str, Any]:
    """Fila del catalogo tal como la consume la pantalla principal."""
    return {
        "deckId": item["deckId"],
        "title": item.get("deckTitle", item["deckId"]),
        "category": item.get("category", "General"),
        "questionCount": item.get("questionCount", 0),
        "updatedAt": item.get("updatedAt", ""),
    }


def serialize_question(item: dict[str, Any]) -> dict[str, Any]:
    """Proyecta un item de DynamoDB al contrato que consume el frontend.

    Se devuelve `isCorrect` en cada opcion porque la tarjeta resuelve el giro
    en cliente, sin segunda llamada. La contrapartida es que la respuesta
    correcta viaja al navegador: sirve para estudiar, no para examinar. Un
    modo evaluacion requeriria omitirla y validar en un `POST /answers`.
    """
    return {
        "questionId": item["questionId"],
        "prompt": item.get("prompt", ""),
        "options": [
            {"text": o.get("text", ""), "isCorrect": bool(o.get("isCorrect", False))}
            for o in item.get("options", [])
        ],
        "explanation": item.get("explanation", ""),
        "position": item.get("position", 0),
    }


def _handle_catalog() -> dict[str, Any]:
    try:
        decks = fetch_catalog()
    except ClientError:
        LOGGER.exception("Fallo la consulta al indice %s", DECKS_INDEX)
        return _response(500, {"message": "Error interno al listar los mazos."})

    return _response(
        200,
        {"count": len(decks), "decks": [serialize_deck(d) for d in decks]},
        cache_seconds=60,
    )


def _handle_deck(deck_id: str) -> dict[str, Any]:
    try:
        meta, questions = fetch_deck(deck_id)
    except ClientError:
        LOGGER.exception("Fallo la consulta a DynamoDB para el mazo %s", deck_id)
        return _response(500, {"message": "Error interno al consultar el mazo."})

    if not questions:
        return _response(404, {"message": f"No existe el mazo '{deck_id}'."})

    meta = meta or {}
    return _response(
        200,
        {
            "deckId": deck_id,
            # El item "#META" es la fuente canonica del titulo; el atributo
            # replicado en cada pregunta solo sirve de respaldo.
            "title": meta.get("deckTitle") or questions[0].get("deckTitle", deck_id),
            "category": meta.get("category", "General"),
            "count": len(questions),
            "questions": [serialize_question(item) for item in questions],
        },
        cache_seconds=60,
    )


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Enruta segun la plantilla de ruta, no segun los parametros recibidos.

    `event["resource"]` trae "/decks" o "/decks/{deckId}" sin interpolar, asi
    que distingue las dos rutas sin ambiguedad. Se cae a `pathParameters` solo
    por robustez ante invocaciones sinteticas.
    """
    resource = event.get("resource") or ""
    deck_id = ((event.get("pathParameters") or {}).get("deckId") or "").strip()

    if deck_id:
        return _handle_deck(deck_id)

    if resource.endswith("{deckId}"):
        return _response(400, {"message": "Falta el parametro deckId."})

    return _handle_catalog()
