"""Ingesta de mazos de flashcards escritos en Markdown.

Disparadores: creacion y borrado de objetos `*.md` en el bucket de mazos.
Salida: un item de DynamoDB por pregunta, mas un item "#META" por mazo.

Organizacion en S3
------------------
La carpeta de primer nivel es la tematica del mazo:

    Bases de Datos/indices-b-tree.md  -> categoria "Bases de Datos"
    Seguridad/iam-basico.md           -> categoria "Seguridad"
    repaso-general.md                 -> categoria "General"

El nombre del archivo sigue siendo el `deckId`.

Dialecto Markdown soportado
---------------------------
    # Titulo del mazo

    ## Enunciado de la pregunta

    - [ ] Opcion incorrecta
    - [x] Opcion correcta

    > Explicacion que se muestra al reverso de la tarjeta.

El parseo es puramente lexico (modulo `re` de la libreria estandar): no se
instala ningun paquete de terceros, asi que el artefacto de despliegue pesa
practicamente cero y arranca en frio mas rapido.
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import unquote_plus

import boto3
from boto3.dynamodb.conditions import Key

LOGGER = logging.getLogger()
LOGGER.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# ---------------------------------------------------------------------------
# Clientes AWS
#
# Se inicializan de forma perezosa para que este modulo pueda importarse (y
# testearse) sin credenciales ni variables de entorno.
# ---------------------------------------------------------------------------
_s3_client = None
_table = None


def _s3():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3")
    return _s3_client


def _questions_table():
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
    return _table


# ---------------------------------------------------------------------------
# Gramatica del dialecto Markdown
# ---------------------------------------------------------------------------
# `^#\s+` no colisiona con `## `: tras la primera almohadilla exige un espacio,
# y en una pregunta el siguiente caracter es otra almohadilla.
TITLE_RE = re.compile(r"^#\s+(?P<title>.+?)\s*$")
QUESTION_RE = re.compile(r"^##\s+(?P<prompt>.+?)\s*$")
OPTION_RE = re.compile(r"^\s*[-*]\s+\[(?P<mark>[ xX])\]\s+(?P<text>.+?)\s*$")
QUOTE_RE = re.compile(r"^>\s?(?P<text>.*?)\s*$")

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")

# Sort key del item de mazo. "#" (0x23) ordena antes que cualquier digito
# hexadecimal, asi que el mazo encabeza siempre su particion.
DECK_SORT_KEY = "#META"

# Valor constante de la PK del indice: un solo Query devuelve todo el catalogo.
CATALOG_PARTITION = "DECK"

DEFAULT_CATEGORY = "General"


# ---------------------------------------------------------------------------
# Modelo de dominio
# ---------------------------------------------------------------------------
@dataclass
class Option:
    text: str
    is_correct: bool


@dataclass
class Question:
    prompt: str
    options: list[Option] = field(default_factory=list)
    explanation_lines: list[str] = field(default_factory=list)

    @property
    def explanation(self) -> str:
        """Reconstruye los parrafos respetando la semantica de Markdown.

        Las lineas consecutivas de un mismo parrafo son *saltos suaves*: el
        autor parte la linea a los 80 caracteres por comodidad, pero al
        renderizar deben unirse con un espacio. Solo una linea en blanco (un
        `>` a solas) separa parrafos de verdad.

        Unirlas con "\n" a secas partia la frase a mitad en la tarjeta,
        porque el componente usa `whitespace-pre-line`.
        """
        paragraphs: list[list[str]] = [[]]

        for line in self.explanation_lines:
            if line.strip():
                paragraphs[-1].append(line.strip())
            elif paragraphs[-1]:
                paragraphs.append([])

        return "\n\n".join(" ".join(p) for p in paragraphs if p).strip()

    @property
    def is_valid(self) -> bool:
        """Una pregunta util necesita opciones y al menos una correcta."""
        return bool(self.options) and any(o.is_correct for o in self.options)


@dataclass
class Deck:
    title: str
    questions: list[Question] = field(default_factory=list)


# Parseo
def parse_markdown(content: str) -> Deck:
    """Convierte el texto de un mazo en un objeto `Deck`.

    Implementado como una maquina de estados de una sola pasada: la unica
    pieza de estado es `current`, la pregunta que se esta construyendo.
    Cualquier linea que no encaje en la gramatica se ignora en silencio, de
    modo que prosa suelta entre preguntas no rompe la ingesta.
    """
    title = ""
    questions: list[Question] = []
    current: Question | None = None

    for raw_line in content.splitlines():
        line = raw_line.rstrip()

        if not line.strip():
            continue

        # El orden importa: `##` se evalua antes que `#`.
        match = QUESTION_RE.match(line)
        if match:
            current = Question(prompt=match.group("prompt"))
            questions.append(current)
            continue

        match = TITLE_RE.match(line)
        if match:
            title = match.group("title")
            continue

        # Opciones y explicaciones solo tienen sentido dentro de una pregunta.
        if current is None:
            continue

        match = OPTION_RE.match(line)
        if match:
            current.options.append(
                Option(
                    text=match.group("text"),
                    is_correct=match.group("mark").lower() == "x",
                )
            )
            continue

        match = QUOTE_RE.match(line)
        if match:
            # Una linea `>` vacia se conserva: preserva los saltos de parrafo.
            current.explanation_lines.append(match.group("text"))

    return Deck(title=title, questions=questions)


def slugify(value: str) -> str:
    """Normaliza texto a un identificador apto para una URL.

    "Fundamentos de AWS (2026)" -> "fundamentos-de-aws-2026"
    """
    ascii_text = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    return _NON_ALNUM_RE.sub("-", ascii_text.lower()).strip("-") or "deck"


def deck_id_from_key(key: str) -> str:
    """Deriva el `deckId` del nombre del archivo en S3.

    `mazos/Fundamentos de AWS.md` -> `fundamentos-de-aws`

    Es la clave que el frontend usara en `GET /decks/{deckId}`, por eso se
    calcula desde la ruta y no desde el titulo: el archivo es la fuente de
    verdad estable aunque se edite el `# Titulo`.
    """
    filename = os.path.basename(key)
    stem = filename[:-3] if filename.lower().endswith(".md") else filename
    return slugify(stem)


def category_from_key(key: str) -> str:
    """Deriva la tematica de la carpeta de primer nivel en S3.

    `Bases de Datos/avanzado/indices.md` -> `Bases de Datos`
    `repaso.md`                          -> `General`

    Se usa el primer nivel y no el directorio inmediato para que las
    subcarpetas sirvan de organizacion interna sin fragmentar el catalogo.
    """
    partes = [p for p in key.split("/") if p]
    return partes[0].strip() if len(partes) > 1 else DEFAULT_CATEGORY


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------
def build_deck_item(
    deck: Deck,
    deck_id: str,
    category: str,
    source_key: str,
    question_count: int,
    timestamp: str,
) -> dict[str, Any]:
    """Construye el item "#META", que es la fila del catalogo.

    `entity` y `catalogSort` solo existen aqui: son las claves de DecksIndex,
    y al no ponerlas en las preguntas el indice queda disperso.
    """
    title = deck.title or deck_id.replace("-", " ").title()

    return {
        "deckId": deck_id,
        "questionId": DECK_SORT_KEY,
        "entity": CATALOG_PARTITION,
        # Ordena el catalogo por tematica y, dentro de ella, por titulo.
        "catalogSort": f"{category}#{title}",
        "deckTitle": title,
        "category": category,
        "questionCount": question_count,
        "sourceKey": source_key,
        "updatedAt": timestamp,
    }


def build_items(deck: Deck, deck_id: str, source_key: str) -> list[dict[str, Any]]:
    """Proyecta el mazo a items de DynamoDB, uno por pregunta valida."""
    timestamp = datetime.now(timezone.utc).isoformat()
    items: list[dict[str, Any]] = []

    for position, question in enumerate(deck.questions):
        if not question.is_valid:
            LOGGER.warning(
                "Pregunta descartada (sin opciones o sin respuesta correcta): %r",
                question.prompt,
            )
            continue

        items.append(
            {
                "deckId": deck_id,
                "questionId": str(uuid.uuid4()),
                "deckTitle": deck.title or deck_id.replace("-", " ").title(),
                "position": position,
                "prompt": question.prompt,
                "options": [
                    {"text": o.text, "isCorrect": o.is_correct} for o in question.options
                ],
                "explanation": question.explanation,
                "sourceKey": source_key,
                "updatedAt": timestamp,
            }
        )

    return items


def _purge_deck(deck_id: str) -> int:
    """Borra las preguntas previas del mazo.

    Como cada ingesta genera `questionId` nuevos (uuid4), sin este barrido una
    reingesta duplicaria el mazo en lugar de reemplazarlo. Se proyectan solo
    las claves para no pagar lectura de los atributos completos.
    """
    table = _questions_table()
    deleted = 0
    kwargs: dict[str, Any] = {
        "KeyConditionExpression": Key("deckId").eq(deck_id),
        "ProjectionExpression": "deckId, questionId",
    }

    with table.batch_writer() as batch:
        while True:
            response = table.query(**kwargs)
            for item in response.get("Items", []):
                batch.delete_item(
                    Key={"deckId": item["deckId"], "questionId": item["questionId"]}
                )
                deleted += 1

            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                break
            kwargs["ExclusiveStartKey"] = last_key

    return deleted


def deck_source_key(deck_id: str) -> str | None:
    """Lee el `sourceKey` del item "#META", o None si el mazo no existe."""
    response = _questions_table().query(
        KeyConditionExpression=Key("deckId").eq(deck_id)
        & Key("questionId").eq(DECK_SORT_KEY),
        ProjectionExpression="sourceKey",
    )
    items = response.get("Items", [])
    return items[0].get("sourceKey") if items else None


def replace_deck(deck_id: str, items: list[dict[str, Any]]) -> int:
    """Reemplaza por completo el mazo: borra lo anterior y escribe lo nuevo.

    No es una operacion atomica; hay una ventana breve en la que el mazo se ve
    vacio. Para un caso de estudio es aceptable. La alternativa de produccion
    seria versionar (`deckId#v2`) y conmutar un puntero al final.
    """
    deleted = _purge_deck(deck_id)
    LOGGER.info("Mazo %s: %d preguntas previas eliminadas", deck_id, deleted)

    table = _questions_table()
    with table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=item)

    return len(items)


# Orquestacion
def process_object(bucket: str, key: str) -> dict[str, Any]:
    """Descarga, parsea y materializa un unico archivo `.md`."""
    LOGGER.info("Procesando s3://%s/%s", bucket, key)

    response = _s3().get_object(Bucket=bucket, Key=key)
    content = response["Body"].read().decode("utf-8")

    deck = parse_markdown(content)
    deck_id = deck_id_from_key(key)
    category = category_from_key(key)
    items = build_items(deck, deck_id, key)

    if not items:
        # Sin preguntas validas no se publica el mazo: el purge deja el
        # catalogo limpio en vez de anunciar un mazo vacio.
        LOGGER.warning("s3://%s/%s no contiene preguntas validas", bucket, key)
        replace_deck(deck_id, [])
        return {"deckId": deck_id, "key": key, "written": 0}

    timestamp = items[0]["updatedAt"]
    meta = build_deck_item(deck, deck_id, category, key, len(items), timestamp)

    written = replace_deck(deck_id, [meta, *items])
    LOGGER.info(
        "Mazo %s [%s]: %d preguntas escritas", deck_id, category, len(items)
    )

    return {
        "deckId": deck_id,
        "key": key,
        "title": meta["deckTitle"],
        "category": category,
        "written": len(items),
    }


def remove_object(key: str) -> dict[str, Any]:
    """Retira del catalogo el mazo cuyo `.md` ha desaparecido.

    LA COMPROBACION DEL `sourceKey` NO ES OPCIONAL
    ----------------------------------------------
    `aws s3 mv` es copiar y borrar, asi que renombrar una CARPETA genera dos
    eventos sobre el mismo `deckId` (el nombre del archivo no cambia):

        PUT    "Cloud Security/iam.md"   -> reingesta el mazo con la categoria nueva
        DELETE "Seguridad/iam.md"        -> ...y este borrado lo destruiria

    Comparando el `sourceKey` almacenado con la clave borrada, ese DELETE se
    ignora: el mazo ya apunta a la ruta nueva. Solo se purga cuando el mazo
    sigue apuntando al archivo que efectivamente se ha ido, que es el caso de
    renombrar el ARCHIVO o borrarlo sin mas.

    Si los eventos llegaran en orden inverso (S3 no garantiza el orden), el
    DELETE purgaria y el PUT posterior reingestaria: el resultado converge.
    """
    deck_id = deck_id_from_key(key)
    almacenado = deck_source_key(deck_id)

    if almacenado is None:
        LOGGER.info("Borrado %s: el mazo %s ya no estaba", key, deck_id)
        return {"deckId": deck_id, "key": key, "removed": 0}

    if almacenado != key:
        LOGGER.info(
            "Borrado %s ignorado: el mazo %s ahora viene de %s",
            key, deck_id, almacenado,
        )
        return {"deckId": deck_id, "key": key, "removed": 0, "supersededBy": almacenado}

    borrados = _purge_deck(deck_id)
    LOGGER.info("Mazo %s retirado del catalogo (%d items)", deck_id, borrados)
    return {"deckId": deck_id, "key": key, "removed": borrados}


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Punto de entrada. Un evento de S3 puede traer varios registros."""
    results = []

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        # Las claves llegan url-encoded: "mis mazos/a.md" -> "mis+mazos/a.md".
        key = unquote_plus(record["s3"]["object"]["key"])

        if not key.lower().endswith(".md"):
            LOGGER.info("Ignorado (no es Markdown): %s", key)
            continue

        # Con versionado activo, un `aws s3 rm` genera DeleteMarkerCreated en
        # lugar de Delete. Ambos significan "el archivo ya no esta".
        if record.get("eventName", "").startswith("ObjectRemoved"):
            results.append(remove_object(key))
        else:
            results.append(process_object(bucket, key))

    return {"processed": results}
