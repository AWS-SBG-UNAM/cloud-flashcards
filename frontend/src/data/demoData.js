/**
 * Datos de respaldo: replican la salida del API para poder ejecutar el
 * frontend sin desplegar nada en AWS.
 */

const fundamentos = {
  deckId: "fundamentos-de-aws",
  title: "Fundamentos de AWS",
  category: "General",
  count: 3,
  questions: [
    {
      questionId: "demo-1",
      position: 0,
      prompt: "¿Que modelo de facturacion de DynamoDB conviene con trafico impredecible?",
      options: [
        { text: "Provisioned con capacidad fija", isCorrect: false },
        { text: "On-Demand (PAY_PER_REQUEST)", isCorrect: true },
        { text: "Reserved Capacity a un año", isCorrect: false },
      ],
      explanation:
        "On-Demand cobra por peticion y escala sin configuracion previa.\n\nProvisioned sale mas barato solo con trafico sostenido y predecible.",
    },
    {
      questionId: "demo-2",
      position: 1,
      prompt: "En una Lambda disparada por S3, ¿de donde se obtiene el nombre del bucket?",
      options: [
        { text: "Del propio evento, en record.s3.bucket.name", isCorrect: true },
        { text: "De una variable de entorno inyectada por CloudFormation", isCorrect: false },
        { text: "Hay que llamar a s3:ListBuckets para descubrirlo", isCorrect: false },
      ],
      explanation:
        "El evento ya trae bucket y clave. Inyectarlo como variable de entorno crearia una dependencia circular en la plantilla SAM.",
    },
    {
      questionId: "demo-3",
      position: 2,
      prompt: "¿Que clave permite leer un mazo completo con un solo Query?",
      options: [
        { text: "Un Scan filtrando por deckId", isCorrect: false },
        { text: "deckId como Partition Key", isCorrect: true },
        { text: "Un indice secundario global sobre prompt", isCorrect: false },
      ],
      explanation:
        "Los items que comparten Partition Key viven en la misma particion logica, asi que un unico Query los recupera. Un Scan leeria la tabla entera.",
    },
  ],
};

const bases = {
  deckId: "indices-b-tree",
  title: "Indices B-Tree",
  category: "Bases de Datos",
  count: 2,
  questions: [
    {
      questionId: "demo-bd-1",
      position: 0,
      prompt: "¿Que complejidad tiene una busqueda en un indice B-Tree equilibrado?",
      options: [
        { text: "O(n)", isCorrect: false },
        { text: "O(log n)", isCorrect: true },
        { text: "O(1)", isCorrect: false },
      ],
      explanation:
        "La altura del arbol crece de forma logaritmica respecto al numero de claves, y cada nivel es una lectura de pagina.",
    },
    {
      questionId: "demo-bd-2",
      position: 1,
      prompt: "¿Por que un indice puede degradar una carga de escritura intensiva?",
      options: [
        { text: "Porque cada INSERT debe actualizar tambien el indice", isCorrect: true },
        { text: "Porque los indices bloquean la tabla entera", isCorrect: false },
        { text: "Porque obligan a usar transacciones serializables", isCorrect: false },
      ],
      explanation:
        "Un indice es una estructura adicional que hay que mantener coherente: cada escritura en la tabla implica al menos otra en el arbol.",
    },
  ],
};

const seguridad = {
  deckId: "iam-basico",
  title: "IAM basico",
  category: "Seguridad",
  count: 2,
  questions: [
    {
      questionId: "demo-sec-1",
      position: 0,
      prompt: "Sin ninguna politica asociada, ¿que puede hacer un rol de IAM?",
      options: [
        { text: "Todo, hasta que se le restrinja", isCorrect: false },
        { text: "Nada: IAM deniega por defecto", isCorrect: true },
        { text: "Solo operaciones de lectura", isCorrect: false },
      ],
      explanation:
        "IAM parte de una denegacion implicita. Los permisos son aditivos y una denegacion explicita siempre gana sobre cualquier permiso.",
    },
    {
      questionId: "demo-sec-2",
      position: 1,
      prompt: "¿Por que conviene evitar las politicas gestionadas amplias?",
      options: [
        { text: "Porque son mas lentas de evaluar", isCorrect: false },
        { text: "Porque conceden mas permisos de los necesarios", isCorrect: true },
        { text: "Porque no se pueden versionar", isCorrect: false },
      ],
      explanation:
        "El principio de minimo privilegio busca conceder solo lo que la carga necesita. Una politica amplia amplia tambien el radio de una credencial comprometida.",
    },
  ],
};

export const demoDecks = Object.fromEntries(
  [fundamentos, bases, seguridad].map((deck) => [deck.deckId, deck]),
);

export const demoCatalog = Object.values(demoDecks).map((deck) => ({
  deckId: deck.deckId,
  title: deck.title,
  category: deck.category,
  questionCount: deck.count,
  updatedAt: "",
}));
