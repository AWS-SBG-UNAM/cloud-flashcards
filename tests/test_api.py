"""Tests de la Lambda de consulta."""

import json


def _put(table, deck_id, question_id, position, prompt):
    table.put_item(
        Item={
            "deckId": deck_id,
            "questionId": question_id,
            "deckTitle": "Fundamentos de AWS",
            "position": position,
            "prompt": prompt,
            "explanation": "porque si",
            "options": [
                {"text": "a", "isCorrect": False},
                {"text": "b", "isCorrect": True},
            ],
        }
    )


def _put_deck(table, deck_id, title, category, count=1):
    """Item "#META": la fila del catalogo que alimenta el indice disperso."""
    table.put_item(
        Item={
            "deckId": deck_id,
            "questionId": "#META",
            "entity": "DECK",
            "catalogSort": f"{category}#{title}",
            "deckTitle": title,
            "category": category,
            "questionCount": count,
            "updatedAt": "2026-08-27T00:00:00+00:00",
        }
    )


def _call(api_app, deck_id):
    return api_app.lambda_handler(
        {"resource": "/decks/{deckId}", "pathParameters": {"deckId": deck_id}}, None
    )


def _call_catalog(api_app):
    return api_app.lambda_handler({"resource": "/decks", "pathParameters": None}, None)


# ---------------------------------------------------------------------------
# GET /decks — catalogo
# ---------------------------------------------------------------------------
def test_el_catalogo_lista_los_mazos(api_app, dynamodb_table):
    _put_deck(dynamodb_table, "indices", "Indices B-Tree", "Bases de Datos", 12)
    _put_deck(dynamodb_table, "iam", "IAM basico", "Seguridad", 8)

    response = _call_catalog(api_app)
    body = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert body["count"] == 2
    assert {d["category"] for d in body["decks"]} == {"Bases de Datos", "Seguridad"}
    assert body["decks"][0]["questionCount"] == 12


def test_el_catalogo_sale_ordenado_por_categoria_y_titulo(api_app, dynamodb_table):
    """`catalogSort` es "categoria#titulo", asi que DynamoDB ya los ordena."""
    _put_deck(dynamodb_table, "z", "Zeta", "Seguridad")
    _put_deck(dynamodb_table, "a", "Alfa", "Bases de Datos")
    _put_deck(dynamodb_table, "m", "Media", "Bases de Datos")

    body = json.loads(_call_catalog(api_app)["body"])

    assert [d["title"] for d in body["decks"]] == ["Alfa", "Media", "Zeta"]


def test_el_catalogo_ignora_las_preguntas(api_app, dynamodb_table):
    """El indice es disperso: sin `entity`, una pregunta no aparece."""
    _put_deck(dynamodb_table, "aws", "Fundamentos de AWS", "General", 1)
    _put(dynamodb_table, "aws", "u1", 0, "Una pregunta")

    body = json.loads(_call_catalog(api_app)["body"])

    assert body["count"] == 1
    assert body["decks"][0]["deckId"] == "aws"


def test_el_catalogo_vacio_responde_200_no_404(api_app, dynamodb_table):
    """Sin mazos, la pantalla principal debe poder pintar su estado vacio."""
    response = _call_catalog(api_app)

    assert response["statusCode"] == 200
    assert json.loads(response["body"])["decks"] == []


# ---------------------------------------------------------------------------
# GET /decks/{deckId} — detalle
# ---------------------------------------------------------------------------
def test_el_titulo_viene_del_item_de_mazo(api_app, dynamodb_table):
    """El "#META" manda sobre el `deckTitle` replicado en cada pregunta."""
    _put_deck(dynamodb_table, "aws", "Titulo canonico", "Redes", 1)
    _put(dynamodb_table, "aws", "u1", 0, "P")

    body = json.loads(_call(api_app, "aws")["body"])

    assert body["title"] == "Titulo canonico"
    assert body["category"] == "Redes"
    assert body["count"] == 1, "el item de mazo no debe contarse como pregunta"
    assert all(q["questionId"] != "#META" for q in body["questions"])


def test_sin_item_de_mazo_recurre_al_titulo_de_la_pregunta(api_app, dynamodb_table):
    _put(dynamodb_table, "aws", "u1", 0, "P")

    body = json.loads(_call(api_app, "aws")["body"])

    assert body["title"] == "Fundamentos de AWS"


def test_devuelve_el_mazo_completo(api_app, dynamodb_table):
    _put(dynamodb_table, "aws", "u1", 0, "Primera")
    _put(dynamodb_table, "aws", "u2", 1, "Segunda")

    response = _call(api_app, "aws")
    body = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert body["deckId"] == "aws"
    assert body["title"] == "Fundamentos de AWS"
    assert body["count"] == 2
    assert [q["prompt"] for q in body["questions"]] == ["Primera", "Segunda"]


def test_ordena_por_position_no_por_el_sort_key(api_app, dynamodb_table):
    """DynamoDB ordena por questionId (uuid, arbitrario). `position` manda."""
    _put(dynamodb_table, "aws", "zzz", 0, "Primera")
    _put(dynamodb_table, "aws", "aaa", 1, "Segunda")

    body = json.loads(_call(api_app, "aws")["body"])

    assert [q["prompt"] for q in body["questions"]] == ["Primera", "Segunda"]


def test_los_decimal_se_serializan_como_int(api_app, dynamodb_table):
    _put(dynamodb_table, "aws", "u1", 0, "P")

    response = _call(api_app, "aws")

    assert "Decimal" not in response["body"]
    assert json.loads(response["body"])["questions"][0]["position"] == 0


def test_aisla_los_mazos_entre_si(api_app, dynamodb_table):
    _put(dynamodb_table, "aws", "u1", 0, "De AWS")
    _put(dynamodb_table, "redes", "u2", 0, "De redes")

    body = json.loads(_call(api_app, "aws")["body"])

    assert body["count"] == 1
    assert body["questions"][0]["prompt"] == "De AWS"


def test_mazo_inexistente_devuelve_404(api_app, dynamodb_table):
    assert _call(api_app, "no-existe")["statusCode"] == 404


def test_deck_id_vacio_en_la_ruta_de_detalle_devuelve_400(api_app, dynamodb_table):
    assert _call(api_app, "   ")["statusCode"] == 400
    assert api_app.lambda_handler(
        {"resource": "/decks/{deckId}", "pathParameters": {}}, None
    )["statusCode"] == 400


def test_un_evento_sin_resource_cae_al_catalogo(api_app, dynamodb_table):
    """Robustez ante invocaciones sinteticas (consola de Lambda, tests)."""
    assert api_app.lambda_handler({}, None)["statusCode"] == 200


def test_emite_la_cabecera_cors(api_app, dynamodb_table):
    """Con REST API el gateway no inyecta CORS en la respuesta del proxy.

    Solo cubre el preflight OPTIONS, asi que la cabecera del GET sale de aqui.
    """
    _put(dynamodb_table, "aws", "u1", 0, "P")

    headers = _call(api_app, "aws")["headers"]

    assert headers["Access-Control-Allow-Origin"] == "*"


def test_la_cabecera_cors_respeta_el_origen_configurado(api_app, dynamodb_table, monkeypatch):
    monkeypatch.setattr(api_app, "CORS_ALLOW_ORIGIN", "https://flashcards.example.dev")
    _put(dynamodb_table, "aws", "u1", 0, "P")

    headers = _call(api_app, "aws")["headers"]

    assert headers["Access-Control-Allow-Origin"] == "https://flashcards.example.dev"


def test_los_errores_tambien_llevan_cors(api_app, dynamodb_table):
    """Sin CORS en el 404, el navegador reporta un error de CORS enganoso."""
    for status_response in (_call(api_app, "no-existe"), _call(api_app, "  ")):
        assert "Access-Control-Allow-Origin" in status_response["headers"]


def test_el_contrato_json_es_utf8_legible(api_app, dynamodb_table):
    dynamodb_table.put_item(
        Item={
            "deckId": "es", "questionId": "u1", "deckTitle": "Programación",
            "position": 0, "prompt": "¿Qué es una lambda?", "explanation": "Una función.",
            "options": [{"text": "Sí", "isCorrect": True}],
        }
    )

    response = _call(api_app, "es")

    assert "¿Qué es una lambda?" in response["body"], "ensure_ascii debe ser False"
    assert json.loads(response["body"])["questions"][0]["options"][0]["isCorrect"] is True
