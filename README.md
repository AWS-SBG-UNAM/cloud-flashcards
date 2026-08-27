# Cloud Flashcards

Aplicación **serverless** que convierte apuntes escritos en Markdown en mazos de
flashcards interactivas. Subes un `.md` a S3 y, sin intervención manual, queda
disponible en una API HTTP que alimenta una tarjeta en React con animación de
giro 3D.

Está pensada como **caso de estudio didáctico**: cada decisión de arquitectura
está comentada en el código, incluidas las que salieron mal a propósito (la
dependencia circular de SAM, el CORS duplicado, la reingesta que duplicaba datos).

---

## Arquitectura

```
  Export de Notion                    Autor del mazo
        │  aws s3 cp                        │  aws s3 cp mazo.md s3://…
        ▼                                   │
┌───────────────────┐                       │
│  S3 · ImportsBucket│                      │
└─────────┬─────────┘                       │
          │ s3:ObjectCreated:* (.md)        │
          ▼                                 │
┌────────────────────────┐                  │
│ Lambda · Normalizer     │                 │
│  Notion -> canonico     │─────────────────┤
└────────────────────────┘                  │
                                            ▼
┌───────────────────┐   s3:ObjectCreated:*
│   S3 · DecksBucket│──(creado o borrado)──────┐
│  (SSE, versionado)│                          │
└───────────────────┘                          ▼
                                    ┌──────────────────────┐
                                    │ Lambda · ParserFunction│
                                    │  python3.12 · arm64    │
                                    │  Markdown → items      │
                                    └───────────┬────────────┘
                                                │ Query + BatchWriteItem
                                                ▼
                                    ┌──────────────────────┐
                                    │ DynamoDB · On-Demand  │
                                    │  PK deckId            │
                                    │  SK questionId        │
                                    │  GSI DecksIndex ······│··> catalogo
                                    └───────────┬────────────┘
                                                │ Query
                                                ▼
┌───────────────────┐  GET /v1/decks          ┌──────────────────────┐
│  React            │  GET /v1/decks/{deckId} │ Lambda · ApiFunction  │
│  DeckPicker +     │◀────────────────────────│                       │
│  Tailwind + motion│   (CORS emitido por     │  python3.12 · arm64   │
└───────────────────┘    la propia Lambda)    └───────────┬───────────┘
        ▲                                                 │
        └────────── API Gateway · REST API (v1) ──────────┘
```

### Flujo completo

1. Subes `fundamentos-de-aws.md` al bucket.
2. S3 emite `s3:ObjectCreated:*` filtrado por sufijo `.md`.
3. `ParserFunction` descarga el objeto, lo parsea con `re` y **reemplaza** el
   mazo en DynamoDB (borra las preguntas previas y escribe las nuevas).
4. La pantalla principal pide `GET /v1/decks` y pinta el catálogo por temática.
5. Al elegir un mazo, pide `GET /v1/decks/{deckId}`.
6. `ApiFunction` resuelve cada petición con **un solo Query** y devuelve JSON.

### El `deckId` sale del nombre del archivo

`mazos/Fundamentos de AWS.md` → `fundamentos-de-aws`

Se deriva de la ruta en S3, no del `# Título`, para que el identificador siga
siendo estable aunque edites el encabezado del documento.

---

## Formato Markdown

```markdown
# Título del mazo

## Enunciado de la pregunta

- [ ] Opción incorrecta
- [x] Opción correcta

> Explicación que aparece al reverso de la tarjeta.
>
> Admite varios párrafos.
```

| Elemento | Sintaxis | Notas |
|---|---|---|
| Título del mazo | `# ` | El primero que aparezca |
| Pregunta | `## ` | Abre una tarjeta nueva |
| Opción | `- [ ]` / `- [x]` | También `* [ ]` y `[X]` mayúscula |
| Explicación | `> ` | Multilínea; `>` solo = salto de párrafo |

Cualquier línea fuera de esta gramática **se ignora en silencio**, así que
puedes intercalar prosa entre preguntas sin romper la ingesta. Una pregunta sin
opciones o sin ninguna respuesta correcta se descarta con un `WARNING` en
CloudWatch en lugar de tumbar la ejecución.

### La carpeta define la temática

La carpeta de primer nivel en S3 es la categoría con la que el mazo aparece
agrupado en la pantalla principal:

```
Bases de Datos/indices-b-tree.md   ->  categoría "Bases de Datos",  deck "indices-b-tree"
Seguridad/iam-basico.md            ->  categoría "Seguridad",       deck "iam-basico"
repaso-general.md                  ->  categoría "General",         deck "repaso-general"
```

Se usa el **primer** nivel, no el directorio inmediato: así las subcarpetas
sirven de organización interna sin fragmentar el catálogo.

Si el archivo no trae `# Título`, se genera uno a partir del nombre
(`redes-tcp-ip.md` → «Redes Tcp Ip»).

Ejemplos completos en [`sample-decks/`](sample-decks/).

---

## Estructura del repositorio

```
template.yaml                        Infraestructura (AWS SAM)
backend/
  normalizer/app.py                  Lambda de importación  Notion → canónico
  parser/app.py                      Lambda de ingesta      S3 → DynamoDB
  api/app.py                         Lambda de consulta     GET /decks[/{deckId}]
frontend/
  src/App.jsx                        Navegación, título, marcador, tema
  src/components/DeckPicker.jsx      Pantalla principal: catálogo por temática
  src/components/Flashcard.jsx       Tarjeta con giro 3D
  src/api/decks.js                   Cliente HTTP
  src/data/demoData.js               Catálogo local para trabajar sin backend
  src/index.css                      Paleta, tipografía y escala global
  public/fonts/                      Amazon Ember (no versionada, ver README)
  e2e/                               Playwright contra AWS real
tests/
  fixtures/                          Mazos de prueba, versionados
  test_*.py                          pytest + moto (AWS simulado)
sample-decks/                        Ignorado por git: contenido de trabajo
  Bases de Datos/ Seguridad/ …       La carpeta define la temática
Makefile                             Atajos de desarrollo
```

---

## Requisitos

| Herramienta | Versión | Para qué |
|---|---|---|
| Python | 3.11+ | Entorno de tests |
| Node.js | 20+ | Frontend |
| Docker | cualquiera | `sam build --use-container` |
| AWS CLI | v2 | Desplegar y subir mazos |

> **Nota sobre la región.** La plantilla usa REST API para poder desplegarse en
> `mx-central-1`. Si tu región soporta API Gateway v2 (la mayoría lo hacen),
> HTTP API sería más barato y simple; ver «Por qué REST API y no HTTP API».

> **Nota sobre el runtime.** Las Lambdas se ejecutan en `python3.12`. Si tu
> Python local es otro (3.13, 3.14…), `sam build` a secas falla con
> `Binary validation failed`. Usa siempre `sam build --use-container`: compila
> dentro de la imagen oficial `public.ecr.aws/sam/build-python3.12`, que es
> además lo que garantiza que las dependencias binarias coincidan con Lambda.

---

## Puesta en marcha

```bash
make entorno          # crea .venv, .venv-sam e instala el frontend
make test             # backend (pytest + moto) y frontend (vitest)
make lint validate    # cfn-lint y sam validate --lint
```

Los entornos quedan separados a propósito:

- `.venv` → `pytest`, `moto`, `cfn-lint`, `boto3`
- `.venv-sam` → `aws-sam-cli`, que fija versiones propias y podría arrastrar
  las del entorno de tests si compartieran venv.

### Frontend sin desplegar nada

```bash
make dev
```

Si `VITE_API_BASE_URL` no está definida, la app arranca con el mazo de
`src/data/demoDeck.js`, que replica el JSON del API. Sirve para trabajar en el
componente sin cuenta de AWS.

---

## Despliegue

```bash
make deploy           # sam build --use-container + sam deploy --guided
```

Al terminar, el stack expone tres outputs:

| Output | Uso |
|---|---|
| `ApiBaseUrl` | Va a `VITE_API_BASE_URL` |
| `DecksBucketName` | Destino de los `.md` en formato canónico |
| `ImportsBucketName` | Destino de los exports de Notion |
| `FlashcardsTableName` | Inspección en la consola de DynamoDB |

Después:

```bash
make seed             # sube el mazo de ejemplo al bucket del stack

cp frontend/.env.example frontend/.env
# pega ApiBaseUrl en VITE_API_BASE_URL

curl "$(aws cloudformation describe-stacks --stack-name cloud-flashcards \
  --region mx-central-1 \
  --query "Stacks[0].Outputs[?OutputKey=='ApiBaseUrl'].OutputValue" \
  --output text)/decks/fundamentos-de-aws"
```

`ApiBaseUrl` ya incluye el stage, así que la ruta completa queda
`https://{apiId}.execute-api.{region}.amazonaws.com/v1/decks/{deckId}`.

### Parámetros de la plantilla

| Parámetro | Por defecto | Descripción |
|---|---|---|
| `ProjectName` | `cloud-flashcards` | Prefijo de todos los recursos |
| `Stage` | `dev` | `dev` \| `staging` \| `prod` |
| `ApiStageName` | `v1` | REST API exige stage; forma parte de la URL |
| `CorsAllowOrigin` | `*` | **Fíjalo al dominio real en producción** |

```bash
sam deploy --parameter-overrides \
  Stage=prod CorsAllowOrigin=https://flashcards.midominio.dev
```

---

## Decisiones de diseño

### Importar desde Notion

Un cuestionario exportado de Notion se sube al **bucket de importaciones** y
aparece en el catálogo sin más pasos:

```
imports/ → NormalizerFunction → decks/ → ParserFunction → DynamoDB
```

Se escribe un `.md` intermedio en vez de ir directo a DynamoDB por dos motivos:
el resultado queda **inspeccionable y editable** cuando la conversión sale rara,
y se reutiliza el pipeline existente sin tocarlo.

> **Los dos buckets son distintos a propósito.** Si la salida cayera en el mismo
> bucket que dispara la función, se invocaría con su propio resultado en bucle
> infinito. Un prefijo (`raw/` → `decks/`) tampoco basta por sí solo: el filtro
> de la notificación es fácil de aflojar sin darse cuenta y el fallo se paga en
> facturación.

#### El formato de Notion es irregular

La respuesta correcta viene codificada en la explicación, pero de formas
distintas dentro del mismo archivo. En un export real de 16 preguntas:

| Forma | Ejemplo | Cuántas |
|---|---|---|
| Prefijo de letra | `c. AWS Auto Scaling…` | 9 |
| Prefijo numérico | `1. Las instancias Spot…` | 4 |
| Sin prefijo alguno | `Los **Dedicated Hosts** permiten…` | 1 |
| Dos respuestas | `d. y e. Las demás opciones…` | 2 |

Y el marcador de bloque aparece como `Respuesta Correcta:` y también como
`Respuesta Correcto:`. Un parser que solo leyera la letra fallaría en 5 de 16.

#### Cascada de estrategias

`resolve_answer` cruza tres pistas en vez de fiarse de una:

1. **Prefijo de letra** — fiable cuando existe. `a`→1ª opción, `d. y e.`→4ª y 5ª.
2. **Cita en el texto** — qué opción nombra la explicación, por solapamiento de
   tokens. Es lo que resuelve las preguntas sin prefijo.
3. **Prefijo numérico** — pista **débil**: en Notion casi siempre es la
   numeración automática de la lista, no la respuesta. Solo se acepta si el
   texto la respalda.

Cuando dos pistas se contradicen, gana la más fiable y queda un `WARNING` en
CloudWatch. Cuando ninguna resuelve, **la pregunta se descarta**: en una app de
estudio una respuesta incorrecta hace más daño que una pregunta que falta.

El informe de cada importación queda en los logs: cuántas se convirtieron, con
qué estrategia, cuáles conviene revisar y cuáles se descartaron.

#### Vista previa local

Antes de subir nada, se puede ver qué produciría la conversión:

```bash
.venv/bin/python backend/normalizer/app.py "mi-cuestionario.md"
```

El Markdown convertido va a stdout y el informe a stderr.

#### El título sale del nombre del archivo

En un export de Notion el archivo lleva el nombre de la página, que es lo que
describe el mazo; el `# H1` suele ser un encabezado interno («Cuestionario #2»)
que no sirve en un catálogo. Además el nombre del archivo ya determina el
`deckId`, así que título e identificador quedan alineados. Si el H1 difiere,
queda anotado en los logs.

### Borrar y renombrar mazos

`ParserFunction` escucha también `s3:ObjectRemoved:*`. Sin eso, borrar o
renombrar un `.md` dejaba el mazo huérfano en el catálogo para siempre.

| Acción | Efecto |
|---|---|
| Renombrar la **carpeta** | El mazo se recategoriza; el `deckId` no cambia |
| Renombrar el **archivo** | Nace un mazo nuevo y el viejo se retira |
| Borrar el `.md` | El mazo desaparece del catálogo |

> **La comprobación del `sourceKey` no es opcional.** `aws s3 mv` es copiar y
> borrar, así que renombrar una carpeta genera dos eventos sobre el mismo
> `deckId`: un `PUT` de la ruta nueva y un `DELETE` de la vieja. Si el `DELETE`
> se procesara a ciegas, destruiría el mazo recién reingestado. Comparando el
> `sourceKey` almacenado con la clave borrada, ese `DELETE` se ignora.
>
> S3 no garantiza el orden de entrega. Con `DELETE` primero, la guarda no
> interviene y es la reingesta posterior la que deja el estado correcto —
> observado así en producción, con 6 ms entre ambos eventos. Los dos órdenes
> convergen, pero un solapamiento realmente concurrente sigue siendo posible en
> teoría; para una colección editada a mano el riesgo es despreciable.

### Por qué REST API y no HTTP API

El diseño original usaba **HTTP API** (API Gateway v2): más barato, con CORS
nativo y URL sin sufijo de stage. El primer despliegue en `mx-central-1` falló:

```
Resource handler returned message: "HTTP APIs are not available in this AWS region"
```

`mx-central-1` no ofrece API Gateway v2. CloudFormation revirtió el stack
entero sin dejar recursos huérfanos. La plantilla migró a **REST API** (v1),
que sí está disponible allí.

> Detalle engañoso: `aws apigatewayv2 get-apis --region mx-central-1` responde
> con una lista vacía en vez de fallar, así que el plano de control existe
> parcialmente. La indisponibilidad solo aparece al **crear** el recurso.

Lo que cambió al migrar:

| | HTTP API (v2) | REST API (v1) |
|---|---|---|
| Stage en la URL | opcional (`$default`) | **obligatorio** (`/v1`) |
| CORS en la respuesta | lo inyecta el gateway | **lo emite la Lambda** |
| CORS del preflight | lo inyecta el gateway | mock `OPTIONS` generado por SAM |
| Errores del gateway | CORS automático | requiere `GatewayResponses` |
| Coste por millón | ~1,00 USD | ~3,50 USD |
| Endpoint | regional | `EndpointConfiguration: REGIONAL` explícito |

### Dependencia circular de SAM

SAM inyecta la `NotificationConfiguration` en el bucket, de modo que **el bucket
depende de la Lambda**. Si la política IAM de esa Lambda usara
`!Ref DecksBucket`, CloudFormation entraría en bucle:

```
DecksBucket → ParserFunction → ParserFunctionRole → DecksBucket
```

Por eso el nombre del bucket se construye con `!Sub` a partir de parámetros y se
repite literal en la política, en lugar de referenciar el recurso.

### Modelo de datos: dos tipos de item, una sola tabla

| Item | PK (`deckId`) | SK (`questionId`) | Para qué |
|---|---|---|---|
| Pregunta | `indices-b-tree` | `<uuid4>` | Contenido de estudio |
| Mazo | `indices-b-tree` | `#META` | Fila del catálogo |

`#` (0x23) ordena antes que cualquier dígito hexadecimal, así que el item de
mazo encabeza siempre su partición. Ambos viven juntos: leer un mazo entero
—metadatos y preguntas— es **un Query**.

`position` guarda el orden original del archivo porque DynamoDB ordena por el
Sort Key, que al ser un UUID es efectivamente aleatorio. La API reordena antes
de responder.

### El catálogo sale de un índice disperso, no de un Scan

Listar los mazos es un patrón de acceso distinto: no parte de un `deckId`
conocido. La salida fácil sería un `Scan` de la tabla entera, que lee también
todas las preguntas y se degrada según crece la colección.

En su lugar, `DecksIndex` usa una **partición constante**:

```
entity      = "DECK"                        <- PK del índice, igual en todos
catalogSort = "Bases de Datos#Indices B-Tree"  <- SK, ya viene ordenado
```

Como solo los items `#META` llevan el atributo `entity`, el índice es
**disperso**: las preguntas ni siquiera se replican en él. El catálogo completo
es un Query sobre una partición con una fila por mazo, y DynamoDB lo devuelve
ya ordenado por temática y título.

> El contrapunto honesto: una partición constante concentra todo el tráfico de
> lectura del catálogo en una sola partición física. Para decenas o cientos de
> mazos es irrelevante; con millones habría que fragmentarla (`DECK#0`…`DECK#9`)
> y consultar los fragmentos en paralelo.

### Reingesta idempotente

Cada pasada genera `questionId` nuevos con `uuid4`, así que volver a subir el
mismo archivo duplicaría el mazo. `ParserFunction` hace *purge + rewrite*:
consulta las preguntas previas proyectando **solo las claves** (no paga la
lectura de los atributos completos) y las borra antes de escribir.

No es atómico: existe una ventana breve en la que el mazo se ve vacío. Es
aceptable para un caso de estudio; en producción se versionaría (`deckId#v2`)
conmutando un puntero al final.

### CORS en tres capas

Con REST API el CORS **no** es automático. Hacen falta tres piezas y omitir
cualquiera rompe el navegador de forma distinta:

1. **Preflight.** La propiedad `Cors` de `AWS::Serverless::Api` genera el
   método `OPTIONS` con integración mock. Los valores llevan comillas simples
   anidadas (`"'*'"`) porque acaban como mapeos de parámetros de respuesta.
2. **Respuesta real.** `backend/api/app.py` emite
   `Access-Control-Allow-Origin` en cada respuesta. El gateway **no** toca las
   respuestas de una integración proxy, así que sin esto el `GET` pasa el
   preflight y aun así el navegador bloquea la lectura.
3. **Errores del gateway.** `GatewayResponses` para `DEFAULT_4XX` y
   `DEFAULT_5XX`. Sin ellos, una ruta inexistente o un throttling llegan sin
   cabeceras y el navegador reporta un «CORS error» engañoso en lugar del
   código real.

Si migraras de vuelta a HTTP API, el punto 2 habría que **quitarlo**: el
gateway ya inyecta la cabecera y duplicarla hace que el navegador rechace la
respuesta.

### Permisos IAM

Se usan `Statement` inline en vez de las políticas prefabricadas de SAM, que
conceden de más: `DynamoDBReadPolicy` incluiría `Scan` y `BatchGetItem`.

| Función | Permisos |
|---|---|
| `ParserFunction` | `s3:GetObject` (solo ese bucket), `dynamodb:Query`, `dynamodb:BatchWriteItem` |
| `ApiFunction` | `dynamodb:Query` |

### Cero dependencias en las Lambdas

El parseo usa solo `re` de la biblioteca estándar y `boto3` ya viene en el
runtime. El artefacto pesa prácticamente nada y el arranque en frío es mínimo.

### La respuesta correcta viaja al navegador

La API devuelve `isCorrect` en cada opción para que la tarjeta resuelva el giro
en cliente, sin una segunda llamada. **Sirve para estudiar, no para evaluar.**
Un modo examen exigiría omitir el campo y validar en un `POST /answers`.

### Identidad visual

Paleta **AWS Builder Center V.01 2025**. Los siete valores de marca se usan
tal cual; los neutros intermedios (superficies, líneas, texto atenuado) son
tintes derivados de Gray 850 y están marcados como tales en `src/index.css`.

| Uso | Color |
|---|---|
| Fondo oscuro / texto claro | Gray 850 `#161D26` |
| Fondo claro | White `#FFFFFF` |
| Acierto | Mint 400 `#00E582` |
| Fallo | Magenta 400 `#FF57E9` |
| Interacción, foco, categoría | Blue 400 `#42B4FF` |
| Acentos de temática | Purple 500 `#AD5CFF`, Amber 400 `#FF9900` |

> **Contraste.** Mint y Magenta sobre blanco no llegan a ratio legible para
> texto (~1,7:1). Por eso en modo claro solo actúan como borde de 2px y como
> fondo de pastilla con texto Gray 850 encima; el cuerpo del texto es siempre
> Gray 850. En modo oscuro, sobre Gray 850, sí funcionan como color de texto.
> El veredicto además nunca depende solo del color: lleva la etiqueta
> «¡Correcto!» / «Incorrecto».

Los acentos de temática se reparten **por posición** en el catálogo, no por
hash del nombre. Con hash, dos temáticas podían caer en el mismo color —pasó
con «General» y «Serverless»— y dos puntos idénticos anulan la pista visual
que aportan.

### Escala de la interfaz

`html { font-size: 120% }` en `src/index.css`. Tailwind expresa espaciado,
tipografía y tamaños en `rem`, así que mover el tamaño base escala toda la
interfaz de forma proporcional, en lugar de retocar cada utilidad. Además
respeta que el usuario haya subido el tamaño de fuente por defecto del
navegador.

### Tipografía

**Amazon Ember**, declarada en `src/index.css`. Los archivos no están
versionados porque la fuente tiene licencia propietaria: colócalos en
`frontend/public/fonts/` siguiendo
[`public/fonts/README.md`](frontend/public/fonts/README.md).

Sin ellos la app funciona igual — `font-display: swap` y la pila de respaldo
hacen que se use la tipografía del sistema.

### El marcador cuenta preguntas, no intentos

El marcador se deriva de un mapa `questionId → acierto`, no de contadores
incrementales. Reintentar una pregunta **sustituye** su entrada:

```
Fallas la 3 de 3           ->  2 de 3 correctas
Reintentas y aciertas      ->  3 de 3 correctas   (no 3 de 4)
Reintentas otras dos veces ->  sigue siendo de 3  (no 4/5, 5/6…)
```

Antes se incrementaba `answered` en cada respuesta, así que cada reintento
inflaba el total. Hay test de regresión en Vitest y en Playwright.

### Detalles del componente

- La perspectiva vive en el contenedor externo; sin ella `rotateY` se ve como un
  aplastamiento plano en vez de un giro con profundidad.
- Las propiedades 3D (`backface-visibility`, `transform-style`) van en `style`
  en línea, no en clases: su nomenclatura cambió entre Tailwind v3 y v4.
- Los colores del veredicto son cadenas literales completas. Tailwind analiza el
  código como texto plano y nunca generaría `bg-${color}-500`.
- Tras responder, el anverso recibe `pointer-events: none`, porque
  `backface-visibility` lo oculta visualmente pero en algunos navegadores sigue
  capturando clics.

---

## Tests

```bash
make test-backend     # 77 tests · pytest + moto (AWS simulado)
make test-frontend    # 26 tests · Vitest + Testing Library (componentes aislados)
make test-e2e         #  3 tests · Playwright en navegador contra AWS real
```

Los tres niveles cubren cosas distintas. `moto` valida la lógica del backend sin
red; Vitest valida el componente con datos fijos; Playwright es el único que
ejerce la cadena completa —`fetch` del DOM → CORS → API Gateway → Lambda →
DynamoDB— y por eso es el que detectó el bug de los saltos suaves.

El backend usa **moto**, que simula S3 y DynamoDB en memoria: no hacen falta
credenciales ni se toca ninguna cuenta real.

Los fixtures viven en `tests/fixtures/` y no en `sample-decks/`: esa carpeta
está en el `.gitignore`, así que la suite no puede depender de su contenido.
`notion-export.md` es sintético y reproduce a propósito todas las rarezas
encontradas en un export real.

`moto` se activa desde un *fixture*, no con el decorador `@mock_aws`. Pytest
resuelve los fixtures **antes** de entrar en el cuerpo del test, así que con el
decorador los clientes se crearían fuera del mock y saldrían a la red de verdad.

Cobertura destacada:

| Test | Qué protege |
|---|---|
| `test_reingesta_reemplaza_en_lugar_de_duplicar` | El purge previo |
| `test_mazo_editado_elimina_las_preguntas_retiradas` | Preguntas borradas del `.md` |
| `test_clave_con_espacios_url_encoded` | S3 entrega las claves con `+` |
| `test_ordena_por_position_no_por_el_sort_key` | Orden real del documento |
| `test_renombrar_la_CARPETA_no_destruye_el_mazo` | La carrera de `aws s3 mv` |
| `test_el_prefijo_numerico_solo_vale_si_el_texto_lo_respalda` | La pista engañosa de Notion |
| `test_no_inventa_cuando_dos_opciones_empatan` | Prefiere no resolver a adivinar |
| `test_ida_y_vuelta_con_el_parser_canonico` | Que la conversión sea digerible |
| `test_el_catalogo_ignora_las_preguntas` | Que el índice siga siendo disperso |
| `test_el_catalogo_sale_ordenado_por_categoria_y_titulo` | Orden desde `catalogSort` |
| `test_el_titulo_viene_del_item_de_mazo` | `#META` como fuente canónica |
| `reintentar SUSTITUYE el resultado` | El bug del marcador |
| `test_emite_la_cabecera_cors` | El REST API no la inyecta solo |
| `test_los_errores_tambien_llevan_cors` | 404 legible en el navegador |
| `bloquea el anverso tras responder` | No cambiar la respuesta tras girar |

---

## Estado de verificación

### Local

| Comprobación | Herramienta | Resultado |
|---|---|---|
| Tests del backend | pytest 9.1.1 + moto 5.2.3 | 77/77 |
| Tests de componentes | Vitest 3.2 + Testing Library | 26/26 |
| Plantilla (lint) | cfn-lint 1.55.1 | limpio |
| Plantilla (SAM) | sam validate --lint | válida |
| Build de las Lambdas | sam build --use-container | correcto (python3.12/arm64) |
| Build del frontend | vite build | correcto |

### Desplegado en AWS

Stack `cloud-flashcards`, cuenta `070053417434`, región `mx-central-1`.

| Comprobación | Resultado |
|---|---|
| Despliegue del stack | `CREATE_COMPLETE` + `UPDATE_COMPLETE` (alta del GSI) |
| Ingesta automática (S3 → Lambda → DynamoDB) | 3 preguntas en ~5 s tras subir el `.md` |
| `GET /v1/decks` (catálogo) | 5 mazos en 4 temáticas, ordenados |
| Ingesta con carpeta de temática | `Bases de Datos/indices-b-tree.md` → categoría correcta |
| `#META` fuera de la lista de preguntas | verificado en la respuesta del detalle |
| `GET /v1/decks/fundamentos-de-aws` | HTTP 200 en 1,03 s |
| Cabecera CORS en la respuesta | `access-control-allow-origin: *` |
| Preflight `OPTIONS` | HTTP 200 con `allow-methods`, `allow-headers`, `max-age` |
| Mazo inexistente | HTTP 404 **con** CORS |
| Ruta inexistente | HTTP 403 del gateway **con** CORS (vía `GatewayResponses`) |
| UTF-8 sin escapar | `¿Que modelo de facturacion…` |
| Reingesta del mismo `.md` | 3 items, no 6; UUID regenerados |
| Mazo editado (2 preguntas fuera, 1 nueva) | quedan 2, título actualizado |
| Permisos IAM mínimos | suficientes; ningún `AccessDenied` en CloudWatch |
| Frontend contra el API real | `vite build` con la URL embebida |

Lo verificado en la nube confirma lo que los tests con `moto` predecían,
incluido el purge que hace idempotente la reingesta.

### En navegador real

`make test-e2e` — Playwright + Chromium contra el API desplegado.

| Comprobación | Resultado |
|---|---|
| `fetch` del DOM a `mx-central-1` | HTTP 200, CORS aceptado por el navegador |
| Catálogo agrupado por temática | Bases de Datos, General, Seguridad, Serverless |
| Un acento distinto por temática | sin colisiones de color |
| Escala global | `getComputedStyle(html).fontSize` = `19.2px` (16 × 1,2) |
| Abrir un mazo cambia el título | h1 y `document.title` pasan al del mazo |
| Volver al catálogo restaura el título | «Cloud Flashcards» |
| Giro al responder mal | reverso Magenta, respuesta correcta revelada |
| Giro al responder bien | reverso Mint |
| **Reintentar no infla el marcador** | `0 de 1` → `1 de 1`, nunca `1 de 2` |
| El marcador se reinicia al cambiar de mazo | verificado |
| Modo oscuro ↔ claro | alterna la clase `dark` en `<html>` |
| Errores de consola | ninguno |
| Mazo inexistente (404 simulado) | mensaje de error, la app no se rompe |

Capturas en `frontend/e2e/.artifacts/`.

> **Bug encontrado aquí.** La tarjeta partía las explicaciones a mitad de frase.
> El parser unía con `\n` las líneas consecutivas de un párrafo, pero en
> Markdown esos son *saltos suaves* que deben unirse con un espacio; solo una
> línea en blanco separa párrafos. Ni `moto` ni Vitest podían verlo: ambos
> comparaban la cadena consigo misma. Corregido en
> `Question.explanation`, con test de regresión en las tres capas.

### Limitación conocida

El formato Markdown **en línea** no se interpreta: `` `código` ``, `**negrita**`
y `_cursiva_` llegan a la tarjeta con sus marcadores literales. El parser es
deliberadamente léxico y el componente renderiza texto plano. Añadirlo requiere
o una dependencia de Markdown o un renderizador propio de fragmentos; ninguna de
las dos entraba en el alcance del caso de estudio.

## Limpieza

```bash
make limpiar
aws s3 rm s3://cloud-flashcards-decks-dev-070053417434-mx-central-1 \
  --recursive --region mx-central-1        # el bucket tiene versionado
sam delete --stack-name cloud-flashcards --region mx-central-1
```

CloudFormation no borra un bucket con objetos dentro; vacíalo primero.

---

## Notas

- El SAM CLI envía telemetría por defecto. El `Makefile` exporta
  `SAM_CLI_TELEMETRY=0`; fuera de él, expórtala en tu shell si quieres evitarla.
- Los log groups se declaran explícitamente con retención de 14 días (sin eso
  son *Never expire*). Si ya existiera un log group con ese nombre creado por
  una Lambda anterior, el despliegue fallaría con `already exists`: bórralo o
  impórtalo antes.
