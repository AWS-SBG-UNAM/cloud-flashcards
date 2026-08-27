import { useState } from "react";
import { motion } from "framer-motion";

/**
 * @typedef {Object} Option
 * @property {string}  text       Texto que se muestra en el boton.
 * @property {boolean} isCorrect  Si esta opcion es la respuesta valida.
 *
 * @typedef {Object} Question
 * @property {string}   questionId
 * @property {string}   prompt
 * @property {Option[]} options
 * @property {string}   explanation
 */

/*
 * Contrato con el backend
 * -----------------------
 * El objeto `question` es, tal cual, un elemento del array `questions` que
 * devuelve `GET /decks/{deckId}` (ver backend/api/app.py):
 *
 *   const res  = await fetch(`${import.meta.env.VITE_API_BASE_URL}/decks/${deckId}`);
 *   const deck = await res.json();
 *   return deck.questions.map((q) => <Flashcard key={q.questionId} question={q} />);
 */

const FLIP_TRANSITION = { duration: 0.6, ease: [0.22, 1, 0.36, 1] };

/*
 * Tailwind analiza el codigo como texto plano, asi que no puede resolver
 * clases construidas en tiempo de ejecucion (`bg-${color}` nunca se genera).
 * Por eso los dos veredictos se declaran como cadenas literales completas.
 *
 * Reparto de color segun contraste (ver nota en index.css): Mint y Magenta
 * sobre blanco no llegan a ratio legible para texto, asi que en modo claro
 * solo actuan como borde y como fondo de pastilla con texto Gray 850 encima.
 * En modo oscuro, sobre Gray 850, si se usan como color de texto.
 */
const VERDICT = {
  correct: {
    label: "¡Correcto!",
    face: "border-aws-mint bg-aws-white dark:bg-aws-surface",
    badge: "bg-aws-mint text-aws-ink",
    accent: "text-aws-ink dark:text-aws-mint",
  },
  incorrect: {
    label: "Incorrecto",
    face: "border-aws-magenta bg-aws-white dark:bg-aws-surface",
    badge: "bg-aws-magenta text-aws-ink",
    accent: "text-aws-ink dark:text-aws-magenta",
  },
};

/*
 * Las propiedades 3D van en `style` y no en clases utilitarias porque su
 * nomenclatura cambio entre Tailwind v3 (`[backface-visibility:hidden]`) y
 * v4 (`backface-hidden`). En linea funcionan igual en ambas versiones.
 */
const FACE_STYLE = {
  backfaceVisibility: "hidden",
  WebkitBackfaceVisibility: "hidden",
};

const BACK_FACE_STYLE = { ...FACE_STYLE, transform: "rotateY(180deg)" };

/*
 * Las dos caras comparten UNA celda de CSS Grid (`col-start-1 row-start-1`)
 * en lugar de apilarse con `absolute inset-0`.
 *
 * Es lo que permite que la tarjeta mida segun su contenido: con posicion
 * absoluta las caras salen del flujo y el contenedor colapsa, lo que obligaba
 * a fijarle un alto arbitrario (26rem) que sobraba en preguntas cortas y se
 * quedaba corto en las largas. Apiladas en la misma celda, la fila mide lo que
 * la cara mas alta y ambas se estiran a ese alto.
 *
 * El giro sigue funcionando porque `transform` no afecta al calculo del
 * layout: la celda se dimensiona con las caras sin rotar.
 *
 * border-2 en vez de border: en modo claro el borde es el portador principal
 * del veredicto, y a 1px la senal quedaba demasiado debil.
 */
const FACE_CLASS =
  "col-start-1 row-start-1 flex flex-col rounded-2xl border-2 p-6 shadow-sm";

/**
 * Tarjeta de estudio que gira sobre el eje Y al responder.
 *
 * @param {Object}   props
 * @param {Question} props.question    Pregunta a mostrar.
 * @param {Function} [props.onAnswered] Callback `({ questionId, isCorrect })`.
 * @param {string}   [props.className]  Clases extra para el contenedor.
 */
export default function Flashcard({ question, onAnswered, className = "" }) {
  const [selectedIndex, setSelectedIndex] = useState(null);

  const options = question.options ?? [];
  const isAnswered = selectedIndex !== null;
  const selectedOption = isAnswered ? options[selectedIndex] : null;
  const isCorrect = Boolean(selectedOption?.isCorrect);
  const verdict = isCorrect ? VERDICT.correct : VERDICT.incorrect;
  const correctOption = options.find((option) => option.isCorrect);

  const handleSelect = (index) => {
    if (isAnswered) return;

    setSelectedIndex(index);
    onAnswered?.({
      questionId: question.questionId,
      isCorrect: Boolean(options[index]?.isCorrect),
      selectedText: options[index]?.text ?? "",
    });
  };

  const handleReset = () => setSelectedIndex(null);

  return (
    // `perspective` en el contenedor externo: sin el, `rotateY` se ve como un
    // aplastamiento plano en lugar de como un giro con profundidad.
    <div
      className={`w-full max-w-2xl ${className}`}
      style={{ perspective: "1200px" }}
    >
      <motion.div
        className="grid"
        style={{ transformStyle: "preserve-3d" }}
        initial={false}
        animate={{ rotateY: isAnswered ? 180 : 0 }}
        transition={FLIP_TRANSITION}
      >
        {/* ---------------------------------------------------------- */}
        {/* Anverso: enunciado y opciones                              */}
        {/* ---------------------------------------------------------- */}
        <section
          className={`${FACE_CLASS} border-aws-mist-line bg-aws-white dark:border-aws-line dark:bg-aws-surface`}
          style={{ ...FACE_STYLE, pointerEvents: isAnswered ? "none" : "auto" }}
          aria-hidden={isAnswered}
        >
          <h3 className="text-lg font-bold leading-snug text-balance break-words text-aws-ink dark:text-aws-white">
            {question.prompt}
          </h3>

          {/* Dos columnas a partir de `sm`: con enunciados u opciones largos,
              una sola columna estiraba la tarjeta muchisimo hacia abajo.
              Los items se estiran al alto de su fila, asi que las opciones de
              longitud dispar quedan alineadas. */}
          <ul className="mt-6 grid gap-2 sm:grid-cols-2">
            {options.map((option, index) => (
              <li key={`${question.questionId}-${index}`} className="flex">
                <button
                  type="button"
                  onClick={() => handleSelect(index)}
                  className="w-full rounded-xl border border-aws-mist-line bg-aws-mist px-4 py-3 text-left text-sm text-balance break-words text-aws-ink transition-colors hover:border-aws-blue focus:outline-none focus-visible:ring-2 focus-visible:ring-aws-blue dark:border-aws-line dark:bg-aws-ink dark:text-aws-white dark:hover:border-aws-blue"
                >
                  {option.text}
                </button>
              </li>
            ))}
          </ul>

          <p className="mt-auto pt-4 text-xs text-aws-muted">
            Elige una opcion para revelar la explicacion.
          </p>
        </section>

        {/* ---------------------------------------------------------- */}
        {/* Reverso: veredicto y explicacion                           */}
        {/* ---------------------------------------------------------- */}
        <section
          className={`${FACE_CLASS} ${verdict.face}`}
          style={{
            ...BACK_FACE_STYLE,
            pointerEvents: isAnswered ? "auto" : "none",
          }}
          aria-hidden={!isAnswered}
          aria-live="polite"
        >
          <span
            className={`self-start rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide ${verdict.badge}`}
          >
            {verdict.label}
          </span>

          <div className="mt-4 space-y-1 text-sm">
            <p className="text-aws-ink dark:text-aws-white">
              Tu respuesta:{" "}
              <span className={`font-medium ${verdict.accent}`}>
                {selectedOption?.text ?? "—"}
              </span>
            </p>

            {!isCorrect && correctOption && (
              <p className="text-aws-ink dark:text-aws-white">
                Respuesta correcta:{" "}
                <span className="font-medium text-aws-ink dark:text-aws-mint">
                  {correctOption.text}
                </span>
              </p>
            )}
          </div>

          {question.explanation && (
            <p className="mt-4 whitespace-pre-line border-t border-aws-mist-line pt-4 text-sm leading-relaxed text-aws-ink dark:border-aws-line dark:text-aws-white">
              {question.explanation}
            </p>
          )}

          <button
            type="button"
            onClick={handleReset}
            className="mt-auto self-start rounded-lg px-3 py-2 text-xs font-medium text-aws-muted transition-colors hover:text-aws-blue focus:outline-none focus-visible:ring-2 focus-visible:ring-aws-blue"
          >
            ← Intentar de nuevo
          </button>
        </section>
      </motion.div>
    </div>
  );
}
