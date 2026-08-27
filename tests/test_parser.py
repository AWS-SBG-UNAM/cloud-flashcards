"""Tests de la Lambda de ingesta."""

from pathlib import Path

import pytest
from conftest import BUCKET_NAME, TABLE_NAME, s3_event

DECK_SK = "#META"


def _split(items):
    """Separa el item de catalogo de los items de pregunta."""
    meta = next((i for i in items if i["questionId"] == DECK_SK), None)
    preguntas = [i for i in items if i["questionId"] != DECK_SK]
    return meta, preguntas

# El fixture vive junto a los tests, no en sample-decks/: esa carpeta esta en
# el .gitignore, asi que la suite no puede depender de su contenido.
SAMPLE = Path(__file__).resolve().parent / "fixtures" / "mazo-canonico.md"


# --------------------------------------------------------------------------
# Parseo puro (sin AWS)
# --------------------------------------------------------------------------
def test_parsea_el_mazo_de_ejemplo(parser_app):
    deck = parser_app.parse_markdown(SAMPLE.read_text(encoding="utf-8"))

    assert deck.title == "Fundamentos de AWS"
    assert len(deck.questions) == 3
    assert all(q.is_valid for q in deck.questions)
    assert all(sum(o.is_correct for o in q.options) == 1 for q in deck.questions)


def test_titulo_no_captura_encabezados_de_pregunta(parser_app):
    deck = parser_app.parse_markdown("# Mazo\n\n## Pregunta\n- [x] si\n")

    assert deck.title == "Mazo"
    assert [q.prompt for q in deck.questions] == ["Pregunta"]


def test_acepta_ambas_vinetas_y_x_mayuscula(parser_app):
    deck = parser_app.parse_markdown("## P\n- [ ] a\n* [X] b\n")
    marks = [(o.text, o.is_correct) for o in deck.questions[0].options]

    assert marks == [("a", False), ("b", True)]


def test_conserva_saltos_de_parrafo_en_la_explicacion(parser_app):
    deck = parser_app.parse_markdown("## P\n- [x] a\n> uno\n>\n> dos\n")

    assert deck.questions[0].explanation == "uno\n\ndos"


def test_une_los_saltos_suaves_con_un_espacio(parser_app):
    """Markdown: partir una linea dentro de un parrafo no crea un salto.

    Antes se unian con "\n" y la tarjeta cortaba la frase a mitad.
    """
    deck = parser_app.parse_markdown(
        "## P\n- [x] a\n> Una frase larga que el autor\n> parte en dos lineas.\n"
    )

    assert deck.questions[0].explanation == "Una frase larga que el autor parte en dos lineas."


def test_combina_saltos_suaves_y_parrafos(parser_app):
    deck = parser_app.parse_markdown(
        "## P\n- [x] a\n> linea uno\n> linea dos\n>\n> otro parrafo\n> continuado\n"
    )

    assert deck.questions[0].explanation == "linea uno linea dos\n\notro parrafo continuado"


def test_ignora_prosa_fuera_de_la_gramatica(parser_app):
    deck = parser_app.parse_markdown("# T\n\nTexto suelto.\n\n## P\n- [x] a\nmas prosa\n")

    assert len(deck.questions) == 1
    assert len(deck.questions[0].options) == 1


def test_pregunta_sin_respuesta_correcta_es_invalida(parser_app):
    deck = parser_app.parse_markdown("## P\n- [ ] a\n- [ ] b\n")

    assert deck.questions[0].is_valid is False
    assert parser_app.build_items(deck, "d", "k") == []


@pytest.mark.parametrize(
    "key,esperado",
    [
        ("Bases de Datos/indices.md", "Bases de Datos"),
        ("Seguridad/avanzado/iam.md", "Seguridad"),
        ("repaso-general.md", "General"),
        ("  Redes  /tcp.md", "Redes"),
    ],
)
def test_categoria_desde_la_carpeta(parser_app, key, esperado):
    assert parser_app.category_from_key(key) == esperado


@pytest.mark.parametrize(
    "key,esperado",
    [
        ("Fundamentos de AWS.md", "fundamentos-de-aws"),
        ("mazos/Programacion Concurrente (2026).MD", "programacion-concurrente-2026"),
        ("acentos/Introducción a Redes.md", "introduccion-a-redes"),
        ("___.md", "deck"),
    ],
)
def test_deck_id_desde_la_clave_de_s3(parser_app, key, esperado):
    assert parser_app.deck_id_from_key(key) == esperado


# --------------------------------------------------------------------------
# Integracion con AWS simulado
# --------------------------------------------------------------------------
def test_ingesta_extremo_a_extremo(parser_app, s3_bucket, dynamodb_table):
    s3_bucket.put_object(
        Bucket=BUCKET_NAME, Key="fundamentos-de-aws.md", Body=SAMPLE.read_bytes()
    )

    result = parser_app.lambda_handler(s3_event(BUCKET_NAME, "fundamentos-de-aws.md"), None)

    assert result["processed"][0]["written"] == 3
    assert result["processed"][0]["deckId"] == "fundamentos-de-aws"

    items = dynamodb_table.query(
        KeyConditionExpression="deckId = :d",
        ExpressionAttributeValues={":d": "fundamentos-de-aws"},
    )["Items"]
    meta, preguntas = _split(items)

    assert len(preguntas) == 3
    assert sorted(int(q["position"]) for q in preguntas) == [0, 1, 2]
    assert all(isinstance(q["options"][0]["isCorrect"], bool) for q in preguntas)

    # El item de catalogo resume el mazo y alimenta el indice disperso.
    assert meta is not None
    assert meta["deckTitle"] == "Fundamentos de AWS"
    assert meta["category"] == "General"
    assert int(meta["questionCount"]) == 3
    assert meta["entity"] == "DECK"
    assert meta["catalogSort"] == "General#Fundamentos de AWS"


def test_solo_el_item_de_mazo_entra_en_el_indice(parser_app, s3_bucket, dynamodb_table):
    """El indice es disperso: las preguntas no llevan `entity`."""
    s3_bucket.put_object(
        Bucket=BUCKET_NAME, Key="Bases de Datos/indices.md",
        Body=b"# Indices\n\n## P\n- [x] si\n",
    )
    parser_app.lambda_handler(s3_event(BUCKET_NAME, "Bases+de+Datos/indices.md"), None)

    meta, preguntas = _split(dynamodb_table.scan()["Items"])

    assert meta["category"] == "Bases de Datos"
    assert meta["catalogSort"] == "Bases de Datos#Indices"
    assert all("entity" not in q for q in preguntas)


def test_titulo_por_defecto_si_falta_el_encabezado(parser_app, s3_bucket, dynamodb_table):
    s3_bucket.put_object(Bucket=BUCKET_NAME, Key="redes-tcp-ip.md", Body=b"## P\n- [x] si\n")

    parser_app.lambda_handler(s3_event(BUCKET_NAME, "redes-tcp-ip.md"), None)
    meta, _ = _split(dynamodb_table.scan()["Items"])

    assert meta["deckTitle"] == "Redes Tcp Ip"


def test_reingesta_reemplaza_en_lugar_de_duplicar(parser_app, s3_bucket, dynamodb_table):
    """El purge previo es lo que hace la ingesta idempotente pese al uuid4."""
    s3_bucket.put_object(
        Bucket=BUCKET_NAME, Key="fundamentos-de-aws.md", Body=SAMPLE.read_bytes()
    )
    event = s3_event(BUCKET_NAME, "fundamentos-de-aws.md")

    parser_app.lambda_handler(event, None)
    _, primeras = _split(dynamodb_table.scan()["Items"])

    parser_app.lambda_handler(event, None)
    meta, segundas = _split(dynamodb_table.scan()["Items"])

    assert len(primeras) == 3
    assert len(segundas) == 3, "la reingesta duplico el mazo"
    # El catalogo no se duplica: "#META" es una clave fija, no un uuid.
    assert sum(1 for i in dynamodb_table.scan()["Items"] if i["questionId"] == DECK_SK) == 1
    assert int(meta["questionCount"]) == 3
    # uuid4 nuevo en cada pasada: los items se reemplazaron, no se sobreescribieron.
    assert {q["questionId"] for q in primeras}.isdisjoint({q["questionId"] for q in segundas})


def test_mazo_editado_elimina_las_preguntas_retiradas(parser_app, s3_bucket, dynamodb_table):
    event = s3_event(BUCKET_NAME, "mazo.md")

    s3_bucket.put_object(
        Bucket=BUCKET_NAME, Key="mazo.md",
        Body=b"# T\n\n## A\n- [x] s\n\n## B\n- [x] s\n\n## C\n- [x] s\n",
    )
    parser_app.lambda_handler(event, None)
    assert len(_split(dynamodb_table.scan()["Items"])[1]) == 3

    s3_bucket.put_object(Bucket=BUCKET_NAME, Key="mazo.md", Body=b"# T\n\n## A\n- [x] s\n")
    parser_app.lambda_handler(event, None)

    meta, preguntas = _split(dynamodb_table.scan()["Items"])
    assert len(preguntas) == 1
    assert preguntas[0]["prompt"] == "A"
    # El contador del catalogo sigue al mazo.
    assert int(meta["questionCount"]) == 1


def test_ignora_objetos_que_no_son_markdown(parser_app, s3_bucket, dynamodb_table):
    result = parser_app.lambda_handler(s3_event(BUCKET_NAME, "notas.txt"), None)

    assert result["processed"] == []


def test_clave_con_espacios_url_encoded(parser_app, s3_bucket, dynamodb_table):
    """S3 entrega las claves codificadas: 'mis mazos/a.md' llega como 'mis+mazos/a.md'."""
    s3_bucket.put_object(Bucket=BUCKET_NAME, Key="mis mazos/a.md", Body=b"## P\n- [x] s\n")

    result = parser_app.lambda_handler(s3_event(BUCKET_NAME, "mis+mazos/a.md"), None)

    assert result["processed"][0]["written"] == 1


def test_markdown_sin_preguntas_validas_no_escribe(parser_app, s3_bucket, dynamodb_table):
    s3_bucket.put_object(Bucket=BUCKET_NAME, Key="vacio.md", Body=b"# Solo titulo\n")

    result = parser_app.lambda_handler(s3_event(BUCKET_NAME, "vacio.md"), None)

    assert result["processed"][0]["written"] == 0
    # Ni preguntas ni fila de catalogo: un mazo vacio no se anuncia.
    assert dynamodb_table.scan()["Items"] == []


# --------------------------------------------------------------------------
# Borrado: s3:ObjectRemoved:*
# --------------------------------------------------------------------------
def _ingest(parser_app, s3_bucket, key, body=b"# T\n\n## P\n- [x] si\n"):
    s3_bucket.put_object(Bucket=BUCKET_NAME, Key=key, Body=body)
    return parser_app.lambda_handler(s3_event(BUCKET_NAME, key), None)


def _remove(parser_app, key, event_name="ObjectRemoved:Delete"):
    return parser_app.lambda_handler(
        s3_event(BUCKET_NAME, key, event_name=event_name), None
    )


def test_borrar_el_md_retira_el_mazo(parser_app, s3_bucket, dynamodb_table):
    _ingest(parser_app, s3_bucket, "Redes/tcp.md")
    assert len(dynamodb_table.scan()["Items"]) == 2  # #META + 1 pregunta

    result = _remove(parser_app, "Redes/tcp.md")

    assert result["processed"][0]["removed"] == 2
    assert dynamodb_table.scan()["Items"] == []


def test_el_borrado_logico_del_versionado_tambien_cuenta(parser_app, s3_bucket, dynamodb_table):
    """Con versionado, `aws s3 rm` emite DeleteMarkerCreated, no Delete."""
    _ingest(parser_app, s3_bucket, "Redes/tcp.md")

    _remove(parser_app, "Redes/tcp.md", event_name="ObjectRemoved:DeleteMarkerCreated")

    assert dynamodb_table.scan()["Items"] == []


def test_renombrar_la_CARPETA_no_destruye_el_mazo(parser_app, s3_bucket, dynamodb_table):
    """La carrera que hace imprescindible comparar el `sourceKey`.

    `aws s3 mv` es copiar y borrar. Al mover de carpeta, el nombre del archivo
    —y por tanto el deckId— no cambia, asi que el DELETE del objeto viejo
    llegaria despues de la reingesta y borraria el mazo recien creado.
    """
    _ingest(parser_app, s3_bucket, "Seguridad/iam.md")
    _ingest(parser_app, s3_bucket, "Cloud Security/iam.md")

    result = _remove(parser_app, "Seguridad/iam.md")

    assert result["processed"][0]["removed"] == 0
    assert result["processed"][0]["supersededBy"] == "Cloud Security/iam.md"

    meta, preguntas = _split(dynamodb_table.scan()["Items"])
    assert meta["category"] == "Cloud Security", "el mazo sobrevivio con la categoria nueva"
    assert len(preguntas) == 1


def test_renombrar_el_ARCHIVO_deja_dos_mazos_y_el_borrado_limpia(
    parser_app, s3_bucket, dynamodb_table
):
    """Aqui el deckId SI cambia, asi que el mazo viejo queda huerfano."""
    _ingest(parser_app, s3_bucket, "Redes/tcp.md")
    _ingest(parser_app, s3_bucket, "Redes/tcp-ip.md")
    assert len({i["deckId"] for i in dynamodb_table.scan()["Items"]}) == 2

    result = _remove(parser_app, "Redes/tcp.md")

    assert result["processed"][0]["removed"] == 2
    assert {i["deckId"] for i in dynamodb_table.scan()["Items"]} == {"tcp-ip"}


def test_borrar_un_mazo_inexistente_no_falla(parser_app, s3_bucket, dynamodb_table):
    result = _remove(parser_app, "Redes/no-existe.md")

    assert result["processed"][0]["removed"] == 0


def test_el_borrado_saca_el_mazo_del_catalogo(parser_app, s3_bucket, dynamodb_table):
    """Sin el item "#META" el mazo desaparece del indice disperso."""
    _ingest(parser_app, s3_bucket, "Redes/tcp.md")

    _remove(parser_app, "Redes/tcp.md")

    assert not [i for i in dynamodb_table.scan()["Items"] if i.get("entity") == "DECK"]


def test_ignora_el_borrado_de_lo_que_no_es_markdown(parser_app, s3_bucket, dynamodb_table):
    _ingest(parser_app, s3_bucket, "Redes/tcp.md")

    result = _remove(parser_app, "Redes/notas.txt")

    assert result["processed"] == []
    assert len(dynamodb_table.scan()["Items"]) == 2
