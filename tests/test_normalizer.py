"""Tests del normalizador de exports de Notion."""

from pathlib import Path

import pytest

from conftest import BUCKET_NAME, IMPORTS_BUCKET, s3_event

FIXTURES = Path(__file__).resolve().parent / "fixtures"
NOTION = FIXTURES / "notion-export.md"
CANONICO = FIXTURES / "mazo-canonico.md"


@pytest.fixture
def notion_md():
    return NOTION.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Deteccion de formato
# ---------------------------------------------------------------------------
def test_reconoce_el_formato_canonico(normalizer_app):
    assert normalizer_app.detect_format(CANONICO.read_text(encoding="utf-8")) == "canonical"


def test_reconoce_el_formato_de_notion(normalizer_app, notion_md):
    assert normalizer_app.detect_format(notion_md) == "notion"


def test_no_reconoce_prosa_suelta(normalizer_app):
    assert normalizer_app.detect_format("# Apuntes\n\nTexto sin preguntas.\n") == "unknown"


# ---------------------------------------------------------------------------
# Extraccion de los marcadores de letra
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "texto,letras,resto",
    [
        ("c. AWS Auto Scaling", ["c"], "AWS Auto Scaling"),
        ("a.  Doble espacio", ["a"], "Doble espacio"),
        ("d) Con parentesis", ["d"], "Con parentesis"),
        ("d. y e. Las demas", ["d", "e"], "Las demas"),
        ("b. y c. Son serverless", ["b", "c"], "Son serverless"),
        ("Sin prefijo alguno", [], "Sin prefijo alguno"),
        ("1. Numero, no letra", [], "1. Numero, no letra"),
    ],
)
def test_extrae_los_prefijos_de_letra(normalizer_app, texto, letras, resto):
    assert normalizer_app._leading_letters(texto) == (letras, resto)


# ---------------------------------------------------------------------------
# Estructura
# ---------------------------------------------------------------------------
def test_extrae_enunciados_y_opciones(normalizer_app, notion_md):
    deck = normalizer_app.parse_notion(notion_md)

    assert deck.title == "Cuestionario #7"
    assert len(deck.questions) == 6
    assert deck.questions[0].options == ["Opcion alfa", "Opcion beta", "Opcion gamma"]


def test_la_numeracion_inconsistente_no_afecta(normalizer_app, notion_md):
    """Notion renumera solo: el "2." de nivel superior es una pregunta mas."""
    deck = normalizer_app.parse_notion(notion_md)

    assert deck.questions[4].prompt.startswith("La numeracion de nivel superior")


def test_tolera_el_typo_respuesta_correcto(normalizer_app, notion_md):
    """El export real trae "Respuesta Correcto:" en algunas preguntas."""
    deck = normalizer_app.parse_notion(notion_md)

    assert deck.questions[2].explanation_lines, "no se leyo el bloque tras el typo"


def test_une_los_saltos_suaves_de_la_explicacion(normalizer_app, notion_md):
    deck = normalizer_app.parse_notion(notion_md)

    assert deck.questions[4].explanation == (
        "b. Segunda, con la explicacion partida en dos lineas del mismo parrafo."
    )


# ---------------------------------------------------------------------------
# Resolucion de la respuesta correcta
# ---------------------------------------------------------------------------
def _resolver(normalizer_app, notion_md):
    deck = normalizer_app.parse_notion(notion_md)
    for q in deck.questions:
        normalizer_app.resolve_answer(q)
    return deck.questions


def test_resuelve_por_prefijo_de_letra(normalizer_app, notion_md):
    q = _resolver(normalizer_app, notion_md)[0]

    assert q.correct == [2]  # "c." -> tercera opcion
    assert "letra" in q.strategy


def test_resuelve_por_texto_cuando_no_hay_prefijo(normalizer_app, notion_md):
    """La explicacion cita "Dedicated Hosts": basta para identificar la opcion."""
    q = _resolver(normalizer_app, notion_md)[1]

    assert q.correct == [1]
    assert q.strategy == "texto (sin prefijo de letra)"


def test_el_prefijo_numerico_solo_vale_si_el_texto_lo_respalda(normalizer_app, notion_md):
    """En Notion el "1." es numeracion de lista, no la respuesta."""
    q = _resolver(normalizer_app, notion_md)[2]

    assert q.correct == [0]
    assert q.strategy == "texto confirmado por el numero"


def test_resuelve_respuestas_multiples(normalizer_app, notion_md):
    q = _resolver(normalizer_app, notion_md)[3]

    assert q.correct == [3, 4]  # "d. y e."
    assert any("solo destaca la primera" in w for w in q.warnings)


def test_deja_sin_resolver_lo_que_no_tiene_pistas(normalizer_app, notion_md):
    q = _resolver(normalizer_app, notion_md)[5]

    assert q.correct == []
    assert "no se pudo deducir" in q.warnings[0]


def test_no_inventa_cuando_dos_opciones_empatan(normalizer_app):
    """Sin ganador destacado se prefiere no resolver a adivinar."""
    q = normalizer_app.RawQuestion(prompt="P", options=["Amazon EC2", "Amazon ECS"])
    q.explanation_lines = ["Ambos son servicios de computo de Amazon."]
    normalizer_app.resolve_answer(q)

    assert q.correct == []


# ---------------------------------------------------------------------------
# Emision
# ---------------------------------------------------------------------------
def test_quita_el_prefijo_de_la_explicacion(normalizer_app, notion_md):
    """En el formato canonico la respuesta la marca `[x]`; la letra sobra."""
    md, _ = normalizer_app.normalize(notion_md, "Mazo")

    assert "> Opcion gamma es la correcta" in md
    assert "> c. Opcion gamma" not in md
    assert "> 1. Las instancias Spot" not in md


def test_descarta_las_preguntas_sin_resolver(normalizer_app, notion_md):
    md, informe = normalizer_app.normalize(notion_md, "Mazo")

    assert informe["found"] == 6
    assert informe["converted"] == 5
    assert len(informe["skipped"]) == 1
    assert "no hay forma de deducir" not in md


def test_el_titulo_sale_del_nombre_del_archivo(normalizer_app):
    """En un export de Notion el archivo lleva el nombre de la pagina; el H1
    suele ser un encabezado interno ("Cuestionario #7")."""
    assert normalizer_app.title_from_key("mazos/Computo en AWS.md") == "Computo en AWS"


def test_el_informe_detalla_las_estrategias(normalizer_app, notion_md):
    _, informe = normalizer_app.normalize(notion_md, "Mazo")

    assert sum(informe["strategies"].values()) == 5
    assert informe["sourceTitle"] == "Cuestionario #7"


# ---------------------------------------------------------------------------
# El resultado tiene que ser digerible por el parser canonico
# ---------------------------------------------------------------------------
def test_ida_y_vuelta_con_el_parser_canonico(normalizer_app, parser_app, notion_md):
    md, _ = normalizer_app.normalize(notion_md, "Mazo importado")
    deck = parser_app.parse_markdown(md)

    assert deck.title == "Mazo importado"
    assert len(deck.questions) == 5
    assert all(q.is_valid for q in deck.questions)
    assert sum(o.is_correct for o in deck.questions[3].options) == 2


# ---------------------------------------------------------------------------
# Integracion con AWS simulado
# ---------------------------------------------------------------------------
def test_escribe_el_mazo_convertido_en_el_bucket_de_mazos(normalizer_app, import_buckets):
    import_buckets.put_object(
        Bucket=IMPORTS_BUCKET, Key="Cloud/quiz.md", Body=NOTION.read_bytes()
    )

    result = normalizer_app.lambda_handler(s3_event(IMPORTS_BUCKET, "Cloud/quiz.md"), None)

    assert result["processed"][0]["written"] is True
    salida = import_buckets.get_object(Bucket=BUCKET_NAME, Key="Cloud/quiz.md")
    contenido = salida["Body"].read().decode("utf-8")

    # La carpeta se conserva, asi que el mazo hereda la tematica "Cloud".
    assert contenido.startswith("# quiz")
    assert "- [x] Opcion gamma" in contenido


def test_un_archivo_ya_canonico_se_copia_sin_tocar(normalizer_app, import_buckets):
    original = CANONICO.read_bytes()
    import_buckets.put_object(Bucket=IMPORTS_BUCKET, Key="ya-canonico.md", Body=original)

    result = normalizer_app.lambda_handler(s3_event(IMPORTS_BUCKET, "ya-canonico.md"), None)

    assert result["processed"][0]["format"] == "canonical"
    copia = import_buckets.get_object(Bucket=BUCKET_NAME, Key="ya-canonico.md")
    assert copia["Body"].read() == original


def test_no_escribe_nada_si_no_reconoce_el_formato(normalizer_app, import_buckets):
    import_buckets.put_object(Bucket=IMPORTS_BUCKET, Key="notas.md", Body=b"# Apuntes\n\nProsa.\n")

    result = normalizer_app.lambda_handler(s3_event(IMPORTS_BUCKET, "notas.md"), None)

    assert result["processed"][0]["written"] is False
    listado = import_buckets.list_objects_v2(Bucket=BUCKET_NAME)
    assert listado.get("KeyCount", 0) == 0


def test_ignora_lo_que_no_es_markdown(normalizer_app, import_buckets):
    result = normalizer_app.lambda_handler(s3_event(IMPORTS_BUCKET, "export.zip"), None)

    assert result["processed"] == []
