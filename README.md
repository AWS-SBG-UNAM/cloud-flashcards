# Cloud Flashcards

Aplicación **serverless** que convierte apuntes en Markdown en mazos de
flashcards interactivas. Subes un `.md` a S3 y queda disponible en una API HTTP
que alimenta una tarjeta en React con giro 3D.

Incluye un importador que convierte cuestionarios exportados desde **Notion** al
formato propio.

Esto está pensando principalmente para crear flashcards sobre los temas necesarios
para las certificaciones de AWS. Pero este proyecto puede expandirse a flashcards
de otros temas.

---

## Arquitectura

Tres Lambdas de Python 3.12, dos buckets S3, una tabla DynamoDB y un REST API
(API Gateway v1). Todo desplegado con SAM.

### Flujo principal: subir un mazo

```
  Autor del mazo
       │
       │  aws s3 cp mazo.md s3://DecksBucket/Categoría/
       ▼
┌────────────────────┐
│  S3 · DecksBucket  │  ← almacena los .md en formato canónico
└─────────┬──────────┘
          │  dispara s3:ObjectCreated:* (filtro sufijo .md)
          ▼
┌────────────────────────┐
│  Lambda · Parser        │  ← backend/parser/app.py
│                         │
│  1. Descarga el .md     │
│  2. Parsea con re:      │
│     # título, ## preg,  │
│     - [x] opciones,     │
│     > explicación       │
│  3. Genera deckId del   │
│     nombre del archivo  │
│  4. Determina categoría │
│     de la carpeta S3    │
│  5. Borra preguntas     │
│     previas (purge)     │
│  6. Escribe items nuevos│
└───────────┬─────────────┘
            │  BatchWriteItem
            ▼
┌────────────────────────┐
│  DynamoDB · On-Demand  │
│                        │
│  Dos tipos de item:    │
│  · Pregunta: PK=deckId │
│    SK=uuid4            │
│  · Mazo: PK=deckId     │
│    SK=#META            │
│                        │
│  GSI DecksIndex:       │
│  PK=entity("DECK")     │
│  SK=categoría#título   │
└───────────┬─────────────┘
            │  Query
            ▼
┌────────────────────┐   GET /v1/decks            ┌────────────────────────┐
│  React             │   GET /v1/decks/{deckId}   │  Lambda · Api           │
│  DeckPicker        │◀───────────────────────────│  backend/api/app.py     │
│  Flashcard (3D)    │                            │  Query DynamoDB         │
└────────────────────┘                            └───────────┬─────────────┘
        ▲                                                   │
        └──────── API Gateway REST API (v1) ────────────────┘
```

### Flujo de Notion

```
  Export de Notion
       │
       │  aws s3 cp cuestionario.md s3://ImportsBucket/Carpeta/
       ▼
┌────────────────────┐
│  S3 · ImportsBucket│  ← bucket separado para evitar bucle infinito
└─────────┬──────────┘
          │  dispara s3:ObjectCreated:*
          ▼
┌────────────────────────────┐
│  Lambda · Normalizer        │  ← backend/normalizer/app.py
│                             │
│  1. Descarga el .md         │
│  2. Detecta formato:        │
│     · canonical → copia     │
│       tal cual              │
│     · notion → normaliza    │
│     · unknown → ignora      │
│  3. Parsea el formato Notion│
│     (listas anidadas,       │
│     marcador Respuesta      │
│     Correcta)               │
│  4. Resuelve la respuesta   │
│     correcta con cascada:   │
│     letra → texto → número  │
│  5. Escribe el .md canónico │
│     en DecksBucket          │
└───────────┬─────────────────┘
            │  PutObject
            ▼
      DecksBucket → ParserFunction → DynamoDB
      (el pipeline normal lo recoge)
```

### Qué hace cada Lambda

| Lambda | Archivo | Dispara | Qué hace |
|---|---|---|---|
| **ParserFunction** | `backend/parser/app.py` | `ObjectCreated` y `ObjectRemoved` en DecksBucket | Parsea el `.md`, genera un item `#META` por mazo + un item por pregunta válida. Reingesta idempotente: borra las previas antes de escribir las nuevas. |
| **NormalizerFunction** | `backend/normalizer/app.py` | `ObjectCreated` en ImportsBucket | Convierte exports de Notion al formato canónico y lo escribe en DecksBucket. El Parser lo recoge después. |
| **ApiFunction** | `backend/api/app.py` | API Gateway (GET) | `GET /decks` devuelve el catálogo (Query sobre DecksIndex). `GET /decks/{deckId}` devuelve todas las preguntas de un mazo (Query por PK). |

### Modelo de datos en DynamoDB

La tabla usa **dos tipos de item en la misma tabla**:

| Tipo | PK (`deckId`) | SK (`questionId`) | Atributos clave |
|---|---|---|---|
| **Mazo** | `indices-b-tree` | `#META` | `entity`, `catalogSort`, `deckTitle`, `category`, `questionCount`, `sourceKey` |
| **Pregunta** | `indices-b-tree` | `<uuid4>` | `prompt`, `options`, `explanation`, `position` |

`#META` (0x23) ordena antes que cualquier UUID, así que el mazo siempre
aparece primero al hacer Query por `deckId`. El catálogo se lee del GSI
`DecksIndex`, donde solo los items `#META` tienen el atributo `entity = "DECK"`:
un solo Query devuelve todos los mazos sin tocar las preguntas.

### S3: dos buckets, no uno

Si la salida del normalizador cayera en el bucket que lo dispara, la Lambda
se invocaría a sí misma en bucle. Dos buckets lo hacen estructuralmente
imposible.

- **DecksBucket**: destino canónico. Tiene versionado activo.
- **ImportsBucket**: recibe exports de Notion u otros formatos ajenos.

### Carpetas en S3 = temática

La carpeta de **primer nivel** define la categoría del mazo:

```
Bases de Datos/indices-b-tree.md   →  categoría "Bases de Datos",  deck "indices-b-tree"
Seguridad/iam-basico.md            →  categoría "Seguridad",       deck "iam-basico"
repaso-general.md                  →  categoría "General",         deck "repaso-general"
```

### CORS en REST API

El REST API (v1) no inyecta cabeceras CORS automáticamente. Hacen falta
tres piezas: el método OPTIONS (mock en el gateway), la cabecera en cada
respuesta de la Lambda, y `GatewayResponses` para errores del gateway.

---

## Requisitos

| Herramienta | Versión | Comprobar           |
| ----------- | ------- | ------------------- |
| Python      | 3.11+   | `python3 --version` |
| Node.js     | 20+     | `node --version`    |
| AWS CLI     | v2      | `aws --version`     |

> Las Lambdas corren en `python3.12`. Usa siempre `make build` (que añade
> `--use-container`) para evitar el error `Binary validation failed`.

---

## Levantar el proyecto

### Credenciales

```bash
aws configure          # o exporta AWS_PROFILE
aws sts get-caller-identity
```

### Instalación

```bash
git clone <repo> && cd cloud-flashcards
make entorno
```

### Tests y validación

```bash
make test      # backend + frontend
make lint      # cfn-lint sobre la plantilla
make validate  # sam validate --lint
```

### Desplegar

```bash
make deploy    # sam build --use-container + sam deploy --guided
```

`--guided` pregunta nombre del stack, región y parámetros. Los defaults
funcionan para desarrollo.

Al terminar, el stack expone cuatro outputs — cópialos para el frontend:

| Output                | Uso                                 |
| --------------------- | ----------------------------------- |
| `ApiBaseUrl`          | Va a `VITE_API_BASE_URL`            |
| `DecksBucketName`     | Bucket destino de `.md` canónicos   |
| `ImportsBucketName`   | Bucket destino de exports de Notion |
| `FlashcardsTableName` | Para inspeccionar en DynamoDB       |

### Conectar el frontend

```bash
make seed                                  # sube un mazo inicial
cp frontend/.env.example frontend/.env     # pega ApiBaseUrl dentro
make dev                                   # http://localhost:5173
```

> `sample-decks/` no se versiona (está en `.gitignore`). En un clon limpio
> `make seed` sube un fixture de `tests/fixtures/` para que el catálogo no
> salga vacío.

---

## Variables de entorno

### Frontend — `frontend/.env`

No se versiona. Plantilla en `frontend/.env.example`.

| Variable            | Qué hace                                                                                    |
| ------------------- | ------------------------------------------------------------------------------------------- |
| `VITE_API_BASE_URL` | URL del API **con el stage** y sin barra final. Si falta, la app usa datos de demostración. |

### Lambdas y parámetros de la plantilla

CloudFormation las inyecta automáticamente. Solo necesitas tocar
`CorsAllowOrigin` en producción:

```bash
sam deploy --parameter-overrides \
  Stage=prod CorsAllowOrigin=https://flashcards.midominio.dev
```

---

## Formato Markdown

```markdown
# Título del mazo

## Enunciado de la pregunta

- [ ] Opción incorrecta
- [x] Opción correcta

> Explicación que aparece al reverso de la tarjeta.
> Pueden ser varias líneas de explicación.
```

Cualquier línea fuera de esta gramática se ignora. Puedes ver ejemplos en
`tests/fixtures/mazo-canonico.md`.

---

## Importar desde Notion

Sube el `.md` exportado al **bucket de importaciones**:

```bash
IMPORTS=$(aws cloudformation describe-stacks --stack-name $STACK --region $REGION \
  --query "Stacks[0].Outputs[?OutputKey=='ImportsBucketName'].OutputValue" --output text)

# Por ejemplo, subimos el mazo "Cómputo en AWS" de la carpeta "Serverless"
aws s3 cp "Serverless/Cómputo en AWS.md" "s3://$IMPORTS/Serverless/" --region $REGION
```

La carpeta se conserva, así que el mazo hereda la temática igual que uno normal.

### Vista previa antes de subir

```bash
.venv/bin/python backend/normalizer/app.py "mi-cuestionario.md"
```

El Markdown convertido sale por stdout y el informe por stderr.

---

## Troubleshooting

### `sam build` falla con `Binary validation failed`

Tu Python local no es 3.12. Usa `make build`, que compila dentro del contenedor.

### `sam build --use-container` no arranca

Docker no está corriendo. Ábrelo y comprueba con `docker info`.

### El navegador dice «CORS error» pero `curl` funciona

Revisa que `backend/api/app.py` emita `Access-Control-Allow-Origin` y que
`CorsAllowOrigin` en la plantilla coincida con tu dominio.

### Subí un `.md` y no aparece

```bash
aws logs tail /aws/lambda/cloud-flashcards-parser-dev --since 10m --region $REGION
```

Causas habituales: el archivo no termina en `.md`, o ninguna pregunta tiene
opción marcada `[x]`.

### La app muestra el catálogo de demostración

`VITE_API_BASE_URL` no está definida o el `.env` se creó después de arrancar
el servidor. Reinicia `npm run dev`.

---

## Limpieza

```bash
make limpiar     # artefactos de build y cachés locales

# CloudFormation no borra buckets con contenido: vacíalos primero.
aws s3 rm "s3://$(aws cloudformation describe-stacks --stack-name $STACK --region $REGION \
  --query "Stacks[0].Outputs[?OutputKey=='DecksBucketName'].OutputValue" --output text)" \
  --recursive --region $REGION
aws s3 rm "s3://$(aws cloudformation describe-stacks --stack-name $STACK --region $REGION \
  --query "Stacks[0].Outputs[?OutputKey=='ImportsBucketName'].OutputValue" --output text)" \
  --recursive --region $REGION

sam delete --stack-name $STACK --region $REGION
```
