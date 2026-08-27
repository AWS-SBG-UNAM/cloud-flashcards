import { motion } from "framer-motion";

/**
 * @typedef {Object} DeckSummary
 * @property {string} deckId
 * @property {string} title
 * @property {string} category
 * @property {number} questionCount
 */

/*
 * Los acentos son cadenas literales completas porque Tailwind analiza el
 * codigo como texto plano: `border-aws-${color}` nunca se generaria.
 *
 * Se reparten por POSICION en el catalogo y no por hash del nombre: con hash,
 * dos tematicas cualesquiera podian caer en el mismo color (paso con
 * "General" y "Serverless"), y dos puntos identicos anulan justamente la
 * pista visual que aportan. Por posicion, los cinco primeros grupos salen
 * siempre distintos. El precio es que anadir una tematica puede desplazar los
 * colores de las siguientes.
 */
const ACCENTS = [
  { dot: "bg-aws-blue", ring: "group-hover:border-aws-blue" },
  { dot: "bg-aws-mint", ring: "group-hover:border-aws-mint" },
  { dot: "bg-aws-purple", ring: "group-hover:border-aws-purple" },
  { dot: "bg-aws-amber", ring: "group-hover:border-aws-amber" },
  { dot: "bg-aws-magenta", ring: "group-hover:border-aws-magenta" },
];

/** Agrupa por tematica conservando el orden que ya trae el API. */
function groupByCategory(decks) {
  const groups = new Map();
  for (const deck of decks) {
    const key = deck.category || "General";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(deck);
  }
  return [...groups.entries()];
}

function DeckCard({ deck, accent, onSelect }) {
  return (
    <button
      type="button"
      onClick={() => onSelect(deck)}
      className={`group flex w-full flex-col items-start gap-2 rounded-2xl border border-aws-mist-line bg-aws-white p-5 text-left transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-aws-blue dark:border-aws-line dark:bg-aws-surface ${accent.ring}`}
    >
      <span className="text-base font-medium text-aws-ink dark:text-aws-white">
        {deck.title}
      </span>
      <span className="text-sm text-aws-muted">
        {deck.questionCount}{" "}
        {deck.questionCount === 1 ? "pregunta" : "preguntas"}
      </span>
    </button>
  );
}

/**
 * Pantalla principal: catalogo de mazos agrupado por tematica.
 *
 * @param {Object}        props
 * @param {DeckSummary[]} props.decks
 * @param {Function}      props.onSelect  Recibe el `DeckSummary` elegido.
 * @param {boolean}       [props.isLoading]
 * @param {string}        [props.error]
 */
export default function DeckPicker({ decks, onSelect, isLoading, error }) {
  if (error) {
    return (
      <p className="rounded-2xl border border-aws-magenta bg-aws-white p-5 text-sm text-aws-ink dark:bg-aws-surface dark:text-aws-white">
        {error}
      </p>
    );
  }

  if (isLoading) {
    return (
      <p className="py-12 text-center text-sm text-aws-muted">
        Cargando mazos…
      </p>
    );
  }

  if (!decks.length) {
    return (
      <div className="rounded-2xl border border-dashed border-aws-mist-line p-8 text-center dark:border-aws-line">
        <p className="text-base font-medium text-aws-ink dark:text-aws-white">
          Todavia no hay mazos
        </p>
        <p className="mt-2 text-sm text-aws-muted">
          Sube un archivo <code className="font-mono">.md</code> al bucket. La
          carpeta de primer nivel define la tematica.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      {groupByCategory(decks).map(([category, items], groupIndex) => {
        const accent = ACCENTS[groupIndex % ACCENTS.length];

        return (
          <motion.section
            key={category}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: groupIndex * 0.06 }}
          >
            <h2 className="mb-3 flex items-center gap-2 text-sm font-medium uppercase tracking-wide text-aws-muted">
              <span className={`h-2 w-2 rounded-full ${accent.dot}`} />
              {category}
              <span className="font-mono normal-case tracking-normal">
                ({items.length})
              </span>
            </h2>

            <div className="grid gap-3 sm:grid-cols-2">
              {items.map((deck) => (
                <DeckCard
                  key={deck.deckId}
                  deck={deck}
                  accent={accent}
                  onSelect={onSelect}
                />
              ))}
            </div>
          </motion.section>
        );
      })}
    </div>
  );
}
