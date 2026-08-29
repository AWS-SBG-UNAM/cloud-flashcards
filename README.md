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

Tres Lambdas de Python 3.14, dos buckets S3, una tabla DynamoDB y un REST API
(API Gateway v1). Todo desplegado con SAM en `mx-central-1`.

El frontend (React + Vite) es un stack aparte: se publica en Amplify Hosting
en `us-east-1`, porque Amplify no está disponible en `mx-central-1`. Ver
[Desplegar el frontend en Amplify](#desplegar-el-frontend-en-amplify-us-east-1).

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
| Python      | 3.14    | `python3 --version` |
| Node.js     | 20+     | `node --version`    |
| AWS CLI     | v2      | `aws --version`     |

> Las Lambdas corren en `python3.14`. Tu Python local debe coincidir (el
> Makefile usa `.venv`, creado sobre esa versión). `make build`/`make deploy`
> empaquetan localmente, sin Docker.

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
make deploy    # sam build local + sam deploy --guided
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

## Desplegar el frontend en Amplify (us-east-1)

El backend vive en `mx-central-1`, pero Amplify Hosting no está disponible
en esa región, así que el frontend se despliega **aparte, en `us-east-1`**
(o cualquier región donde Amplify esté disponible). Son dos stacks
independientes que solo se conectan a través de `ApiBaseUrl` y CORS.

### Opción A — Consola de Amplify (recomendada)

1. En la consola de Amplify (región `us-east-1`) → **New app → Host web app**.
2. Conecta el repositorio de GitHub (la primera vez pide instalar la
   GitHub App de Amplify) y elige la rama a publicar.
3. Como el frontend vive en `frontend/` y no en la raíz del repo, activa
   **Monorepo** y fija el *App root* a `frontend`. Amplify recogerá
   `frontend/amplify.yml` automáticamente.
4. En **App settings → Environment variables**, agrega:

   | Variable              | Valor                                         |
   | --------------------- | ---------------------------------------------- |
   | `VITE_API_BASE_URL`   | El `ApiBaseUrl` que imprimió `make deploy`     |

5. Guarda y despliega. Amplify publica en `https://<rama>.<app-id>.amplifyapp.com`.
6. Actualiza CORS en el backend con esa URL (ver más abajo) y vuelve a
   desplegar `template.yaml`.

### Opción B — CloudFormation (`amplify.template.yaml`)

Para quienes prefieren IaC en vez de configurar la consola a mano. Requiere
un [personal access token de GitHub](https://docs.aws.amazon.com/amplify/latest/userguide/setting-up-GitHub-access.html)
con permiso `repo` (no se guarda en el repo ni en el stack; solo se usa en
el momento del despliegue).

```bash
make amplify-deploy \
  API_BASE_URL=https://xxxxxxxxxx.execute-api.mx-central-1.amazonaws.com/v1 \
  GITHUB_ACCESS_TOKEN=ghp_xxx

make amplify-url    # imprime la URL publicada
```

`REGION_FRONTEND` (default `us-east-1`) y `STACK_FRONTEND` en el Makefile
controlan región y nombre de este stack, igual que `REGION`/`STACK` hacen
para el backend. En un fork, cambia también el parámetro `Repository` de
`amplify.template.yaml` (o pásalo con `--parameter-overrides` si editas el
target) para que apunte a tu propio repositorio.

Para retirar el stack: `aws cloudformation delete-stack --stack-name
$(STACK_FRONTEND) --region $(REGION_FRONTEND)`.

### Coordinar CORS entre regiones

El backend (`mx-central-1`) por defecto acepta `CorsAllowOrigin=*`. Una vez
que conoces la URL de Amplify, ciérrala al dominio real y vuelve a
desplegar el backend:

```bash
sam deploy --stack-name $(STACK) --region mx-central-1 \
  --parameter-overrides CorsAllowOrigin=https://main.xxxxxxxxxx.amplifyapp.com
```

Si usas un dominio propio conectado en Amplify, usa ese dominio en vez del
`*.amplifyapp.com` por defecto.

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

Tu Python local no coincide con el runtime `python3.14` de la plantilla.
Recrea el `.venv` con Python 3.14 (`make entorno`).

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
make clean
```

Borra los artefactos locales (`.aws-sam`, `dist`, caches) y retira el
despliegue de AWS: vacía primero los buckets (CloudFormation se niega a borrar
buckets con contenido) y después hace `sam delete`. Respeta `STACK` y `REGION`
del Makefile.
```
