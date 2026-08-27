"""Normalizador de cuestionarios exportados desde Notion.

Disparador: creacion de un objeto `*.md` en el bucket de importaciones.
Salida: el mismo mazo en el formato canonico, escrito en el bucket de mazos,
donde `ParserFunction` lo recoge y lo materializa en DynamoDB.

    imports/  -->  NormalizerFunction  -->  decks/  -->  ParserFunction  -->  DynamoDB

Se escribe un `.md` intermedio en vez de ir directo a DynamoDB por dos motivos:
el resultado queda inspeccionable y editable a mano cuando algo sale raro, y se
reutiliza el pipeline existente sin tocarlo.

Los dos buckets son distintos a proposito: si la salida cayera en el mismo
bucket que dispara esta funcion, se invocaria a si misma en bucle infinito.

Formato de Notion
-----------------
    # Cuestionario #2

    1. Enunciado de la pregunta
        1. Primera opcion
        2. Segunda opcion
        - Respuesta Correcta:

            c. Explicacion, prefijada por la letra de la opcion correcta.

La numeracion de Notion no es fiable (Markdown renumera solo) y el marcador de
respuesta aparece de varias formas. Ver `resolve_answer` para la cascada de
estrategias que resuelve cual es la opcion correcta.
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote_plus

import boto3

LOGGER = logging.getLogger()
LOGGER.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

_s3_client = None


def _s3():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3")
    return _s3_client


# Gramatica del export de Notion
TITLE_RE = re.compile(r"^#\s+(?P<title>.+?)\s*$")
ORDERED_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<num>\d+)[.)]\s+(?P<text>.+?)\s*$")
BULLET_RE = re.compile(r"^(?P<indent>[ \t]*)[-*+]\s+(?P<text>.+?)\s*$")

# "Respuesta Correcta:", y tambien el "Respuesta Correcto:" que aparece en
# exports reales. Se admite singular, plural y ambos generos. Tambien
# admite negrita alrededor (**Respuesta Correcta**).
ANSWER_MARKER_RE = re.compile(r"^\*{0,2}respuestas?\s+correct[ao]s?\s*\*{0,2}:?\s*$", re.IGNORECASE)

# Prefijo de letra al principio de la explicacion: "c. ", "d) ".
LETTER_RE = re.compile(r"^([a-zA-Z])\s*[.)]\s+")
# Conector entre dos letras: "d. y e. ", "b. y c. ".
CONNECTOR_RE = re.compile(r"^(?:y|e|,|and|&)\s+", re.IGNORECASE)
# Prefijo numerico, que en Notion suele ser numeracion de lista, no respuesta.
NUMBER_RE = re.compile(r"^(\d+)\s*[.)]\s+")

# Un archivo ya canonico trae encabezados de nivel 2 y casillas de tarea.
CANONICAL_RE = re.compile(r"^##\s+.+$.*?^\s*[-*]\s+\[[ xX]\]\s+", re.M | re.S)

# Palabras demasiado comunes para discriminar entre opciones.
STOPWORDS = frozenset(
    """de la el los las un una y o en para con del al que es su sus por se lo
    a como mas o u aws amazon instancias instancia servicio servicios usar
    opcion opciones siguientes cual cuales""".split()
)


@dataclass
class RawQuestion:
    prompt: str
    options: list[str] = field(default_factory=list)
    explanation_lines: list[str] = field(default_factory=list)
    correct: list[int] = field(default_factory=list)
    strategy: str = "sin resolver"
    warnings: list[str] = field(default_factory=list)

    @property
    def explanation(self) -> str:
        """Une los saltos suaves y conserva los saltos de parrafo."""
        paragraphs: list[list[str]] = [[]]
        for line in self.explanation_lines:
            if line.strip():
                paragraphs[-1].append(line.strip())
            elif paragraphs[-1]:
                paragraphs.append([])
        return "\n\n".join(" ".join(p) for p in paragraphs if p).strip()


@dataclass
class NotionDeck:
    title: str = ""
    questions: list[RawQuestion] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Deteccion de formato
# ---------------------------------------------------------------------------
def detect_format(content: str) -> str:
    """Devuelve "canonical", "notion" o "unknown"."""
    if CANONICAL_RE.search(content):
        return "canonical"

    # Notion: al menos un item ordenado sin sangrar y un marcador de respuesta.
    tiene_preguntas = any(
        m and not m.group("indent") for m in map(ORDERED_RE.match, content.splitlines())
    )
    tiene_marcador = any(
        ANSWER_MARKER_RE.match(m.group("text"))
        for m in filter(None, map(BULLET_RE.match, content.splitlines()))
    )
    return "notion" if tiene_preguntas and tiene_marcador else "unknown"


# Parseo
def _indent_width(indent: str) -> int:
    return len(indent.replace("\t", "    "))


def parse_notion(content: str) -> NotionDeck:
    """Recorre el export en una pasada, guiandose por la sangria.

    Nivel 0 -> enunciado; nivel 1 -> opcion o marcador de respuesta;
    nivel 2 en adelante -> explicacion.
    """
    deck = NotionDeck()
    current: RawQuestion | None = None
    in_answer = False

    for raw_line in content.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            # Dentro del bloque de respuesta, la linea vacia separa parrafos.
            if current is not None and in_answer:
                current.explanation_lines.append("")
            continue

        titulo = TITLE_RE.match(line)
        if titulo and not deck.title:
            deck.title = titulo.group("title")
            continue

        ordered = ORDERED_RE.match(line)
        bullet = BULLET_RE.match(line)
        indent = _indent_width((ordered or bullet).group("indent")) if (ordered or bullet) else 99

        # --- Nuevo enunciado ---------------------------------------------
        if ordered and indent == 0:
            current = RawQuestion(prompt=ordered.group("text"))
            deck.questions.append(current)
            in_answer = False
            continue

        if current is None:
            continue

        # --- Marcador de respuesta ---------------------------------------
        if bullet and ANSWER_MARKER_RE.match(bullet.group("text")):
            in_answer = True
            continue

        # --- Opcion --------------------------------------------------------
        if ordered and not in_answer and 0 < indent <= 5:
            current.options.append(ordered.group("text"))
            continue

        # --- Explicacion ----------------------------------------------------
        if in_answer:
            texto = (ordered or bullet).group("text") if (ordered or bullet) else line.strip()
            # Una explicacion anidada como item de lista conserva su numero,
            # que resolve_answer usa despues como pista debil.
            if ordered:
                texto = f"{ordered.group('num')}. {texto}"
            current.explanation_lines.append(texto)

    return deck



# Resolucion de la respuesta correcta
def _fold(text: str) -> str:
    """Minusculas sin acentos ni puntuacion, para comparar."""
    ascii_text = (
        unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    )
    return re.sub(r"[^a-z0-9\s]", " ", ascii_text.lower())


def _tokens(text: str) -> set[str]:
    return {t for t in _fold(text).split() if t and t not in STOPWORDS}


def strip_answer_prefix(explanation: str) -> str:
    """Quita el "c. " o "d. y e. " del principio: en el formato canonico la
    respuesta la marca el `[x]`, asi que el prefijo sobra."""
    _, resto = _leading_letters(explanation)
    if resto != explanation:
        return resto
    numero = NUMBER_RE.match(explanation)
    return explanation[numero.end():] if numero else explanation


def _leading_letters(text: str) -> tuple[list[str], str]:
    """Extrae los marcadores de letra iniciales y devuelve el resto.

    "c. AWS Auto Scaling"      -> (["c"], "AWS Auto Scaling")
    "d. y e. Las demas opciones" -> (["d", "e"], "Las demas opciones")
    """
    letters: list[str] = []
    rest = text.lstrip()

    while True:
        m = LETTER_RE.match(rest)
        if not m:
            break
        letters.append(m.group(1).lower())
        rest = rest[m.end():]

        conector = CONNECTOR_RE.match(rest)
        if not conector:
            break
        rest = rest[conector.end():]

    return letters, rest


def _by_letter(explanation: str, option_count: int) -> list[int]:
    """Indices deducidos del prefijo de letra (a=0, b=1, ...)."""
    letters, _ = _leading_letters(explanation)
    indices = [ord(l) - ord("a") for l in letters]
    return indices if all(0 <= i < option_count for i in indices) else []


def _by_number(explanation: str, option_count: int) -> list[int]:
    """Indice deducido de un prefijo numerico.

    Pista DEBIL: en Notion casi siempre es la numeracion automatica de la
    lista, no la respuesta. Solo se usa si el texto la respalda.
    """
    m = NUMBER_RE.match(explanation.lstrip())
    if not m:
        return []
    indice = int(m.group(1)) - 1
    return [indice] if 0 <= indice < option_count else []


def _by_text(explanation: str, options: list[str]) -> list[int]:
    """Indice de la opcion cuyo texto aparece citado en la explicacion.

    Es la estrategia mas robusta cuando falta el prefijo: quien escribe la
    explicacion casi siempre nombra la opcion correcta. Se exige un ganador
    unico y destacado para no adivinar.
    """
    contexto = _tokens(explanation)
    if not contexto:
        return []

    puntuaciones = []
    for indice, opcion in enumerate(options):
        tokens = _tokens(opcion)
        if not tokens:
            puntuaciones.append((0.0, indice))
            continue
        puntuaciones.append((len(tokens & contexto) / len(tokens), indice))

    puntuaciones.sort(reverse=True)
    mejor, segundo = puntuaciones[0], (puntuaciones[1] if len(puntuaciones) > 1 else (0.0, -1))

    # Umbral: coincidencia sustancial y separacion clara sobre la siguiente.
    if mejor[0] >= 0.5 and mejor[0] - segundo[0] >= 0.25:
        return [mejor[1]]
    return []


def resolve_answer(question: RawQuestion) -> None:
    """Decide la opcion correcta cruzando varias estrategias.

    Las pistas se corroboran entre si en vez de confiar en una sola: el
    prefijo de letra es fiable cuando existe, pero falta en bastantes
    preguntas, y el prefijo numerico engaña porque Markdown renumera solo.
    """
    explicacion = question.explanation
    if not question.options:
        question.warnings.append("sin opciones")
        return
    if not explicacion:
        question.warnings.append("sin bloque de respuesta")
        return

    por_letra = _by_letter(explicacion, len(question.options))
    por_texto = _by_text(explicacion, question.options)
    por_numero = _by_number(explicacion, len(question.options))

    if por_letra:
        question.correct = por_letra
        if len(por_letra) > 1:
            question.strategy = "letra (respuesta multiple)"
            question.warnings.append(
                f"{len(por_letra)} respuestas correctas; la tarjeta solo destaca la primera"
            )
        elif por_texto and por_texto != por_letra:
            question.strategy = "letra (el texto sugiere otra)"
            question.warnings.append(
                f"la letra apunta a la opcion {por_letra[0] + 1} pero el texto "
                f"cita la {por_texto[0] + 1}: conviene revisarla"
            )
        else:
            question.strategy = "letra confirmada por el texto" if por_texto else "letra"
        return

    if por_texto:
        question.correct = por_texto
        question.strategy = (
            "texto confirmado por el numero"
            if por_numero == por_texto
            else "texto (sin prefijo de letra)"
        )
        if por_numero and por_numero != por_texto:
            question.warnings.append(
                f"el numero apunta a la opcion {por_numero[0] + 1} y el texto a la "
                f"{por_texto[0] + 1}; se usa el texto"
            )
        return

    question.warnings.append("no se pudo deducir la respuesta correcta")


# ---------------------------------------------------------------------------
# Emision del formato canonico
# ---------------------------------------------------------------------------
def to_canonical(deck: NotionDeck, title: str) -> str:
    """Serializa al dialecto que entiende `backend/parser/app.py`."""
    lineas = [f"# {title}", ""]

    for question in deck.questions:
        if not question.correct:
            continue

        lineas.append(f"## {question.prompt}")
        lineas.append("")
        for indice, opcion in enumerate(question.options):
            marca = "x" if indice in question.correct else " "
            lineas.append(f"- [{marca}] {opcion}")
        lineas.append("")

        explicacion = strip_answer_prefix(question.explanation)
        if explicacion:
            for parrafo in explicacion.split("\n\n"):
                lineas.append(f"> {parrafo}")
                lineas.append(">")
            lineas.pop()  # sobra el ">" final
            lineas.append("")

    return "\n".join(lineas).rstrip() + "\n"


def normalize(content: str, title: str) -> tuple[str, dict[str, Any]]:
    """Convierte un export de Notion al formato canonico.

    Devuelve el Markdown y un informe con lo que hubo que deducir, para que
    quede en CloudWatch en vez de perderse.
    """
    deck = parse_notion(content)
    for question in deck.questions:
        resolve_answer(question)

    resueltas = [q for q in deck.questions if q.correct]
    descartadas = [q for q in deck.questions if not q.correct]
    revisar = [q for q in resueltas if q.warnings]

    informe = {
        "sourceTitle": deck.title,
        "found": len(deck.questions),
        "converted": len(resueltas),
        "skipped": [{"prompt": q.prompt[:80], "why": q.warnings} for q in descartadas],
        "review": [
            {"prompt": q.prompt[:80], "strategy": q.strategy, "notes": q.warnings}
            for q in revisar
        ],
        "strategies": {q.strategy: 0 for q in resueltas},
    }
    for q in resueltas:
        informe["strategies"][q.strategy] += 1

    return to_canonical(deck, title), informe


# ---------------------------------------------------------------------------
# Orquestacion
# ---------------------------------------------------------------------------
def title_from_key(key: str) -> str:
    """El nombre del archivo manda sobre el `# H1` del documento.

    En un export de Notion el archivo lleva el nombre de la pagina, que es lo
    que describe el mazo; el H1 suele ser un encabezado interno ("Cuestionario
    #2") que no sirve de titulo en el catalogo. Ademas el nombre del archivo ya
    determina el `deckId`, asi que titulo e identificador quedan alineados.
    """
    nombre = os.path.basename(key)
    return nombre[:-3] if nombre.lower().endswith(".md") else nombre


def process_object(bucket: str, key: str, destino: str) -> dict[str, Any]:
    LOGGER.info("Normalizando s3://%s/%s", bucket, key)

    content = _s3().get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
    formato = detect_format(content)
    titulo = title_from_key(key)

    if formato == "canonical":
        LOGGER.info("%s ya esta en formato canonico: se copia sin tocar", key)
        salida = content
        informe = {"format": "canonical", "converted": None}
    elif formato == "notion":
        salida, informe = normalize(content, titulo)
        informe["format"] = "notion"
        if informe["sourceTitle"] and informe["sourceTitle"] != titulo:
            LOGGER.info(
                "Titulo tomado del archivo (%r); el H1 del documento era %r",
                titulo, informe["sourceTitle"],
            )
        if not informe["converted"]:
            LOGGER.warning("%s: ninguna pregunta convertida, no se escribe nada", key)
            return {"key": key, "written": False, **informe}
        for aviso in informe["skipped"]:
            LOGGER.warning("Pregunta descartada (%s): %s", aviso["why"], aviso["prompt"])
        for aviso in informe["review"]:
            LOGGER.warning("Pregunta a revisar (%s): %s", aviso["notes"], aviso["prompt"])
    else:
        LOGGER.warning("%s: formato no reconocido, se ignora", key)
        return {"key": key, "written": False, "format": "unknown"}

    _s3().put_object(
        Bucket=destino,
        Key=key,
        Body=salida.encode("utf-8"),
        ContentType="text/markdown; charset=utf-8",
    )
    LOGGER.info("Escrito s3://%s/%s", destino, key)

    return {"key": key, "written": True, **informe}


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    destino = os.environ["DECKS_BUCKET"]
    resultados = []

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])

        if not key.lower().endswith(".md"):
            LOGGER.info("Ignorado (no es Markdown): %s", key)
            continue

        resultados.append(process_object(bucket, key, destino))

    return {"processed": resultados}


# Vista previa local: `python backend/normalizer/app.py archivo.md`
if __name__ == "__main__":  # pragma: no cover
    import json
    import sys

    ruta = sys.argv[1]
    with open(ruta, encoding="utf-8") as fh:
        texto = fh.read()

    md, reporte = normalize(texto, title_from_key(ruta))
    print(json.dumps(reporte, indent=2, ensure_ascii=False), file=sys.stderr)
    print(md)
