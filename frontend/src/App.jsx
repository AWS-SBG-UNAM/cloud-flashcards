import { useCallback, useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

import DeckPicker from "./components/DeckPicker.jsx";
import Flashcard from "./components/Flashcard.jsx";
import { fetchDeck, fetchDecks, hasBackend } from "./api/decks.js";
import { demoCatalog, demoDecks } from "./data/demoData.js";

const APP_TITLE = "Cloud Flashcards";

/** Conmuta la clase `dark` en <html>, que es lo que lee Tailwind. */
function useDarkMode() {
  const [isDark, setIsDark] = useState(() =>
    document.documentElement.classList.contains("dark"),
  );

  useEffect(() => {
    document.documentElement.classList.toggle("dark", isDark);
  }, [isDark]);

  return [isDark, () => setIsDark((value) => !value)];
}

export default function App() {
  const [catalog, setCatalog] = useState(hasBackend ? null : demoCatalog);
  const [catalogError, setCatalogError] = useState(null);

  // `selected` es el resumen del catalogo: da titulo y tematica al instante,
  // antes de que lleguen las preguntas. `deck` es la carga completa.
  const [selected, setSelected] = useState(null);
  const [deck, setDeck] = useState(null);
  const [deckError, setDeckError] = useState(null);

  const [index, setIndex] = useState(0);
  /*
   * El marcador se deriva de un mapa questionId -> acierto, no de contadores
   * incrementales. Reintentar una pregunta SUSTITUYE su entrada en vez de
   * anadir una nueva, asi que fallar la 3 de 3 y reintentarla sigue siendo
   * "de 3 contestadas" y no 3/4, 4/5, 5/6...
   */
  const [results, setResults] = useState({});

  const [isDark, toggleDark] = useDarkMode();

  // --- Catalogo ---------------------------------------------------------
  useEffect(() => {
    if (!hasBackend) return undefined;

    const controller = new AbortController();
    fetchDecks({ signal: controller.signal })
      .then(setCatalog)
      .catch((error) => {
        if (error.name !== "AbortError") setCatalogError(error.message);
      });

    return () => controller.abort();
  }, []);

  // --- Titulo de la pestana, sincronizado con la pantalla ---------------
  useEffect(() => {
    document.title = selected ? `${selected.title} · ${APP_TITLE}` : APP_TITLE;
  }, [selected]);

  // --- Navegacion -------------------------------------------------------
  const openDeck = useCallback(async (summary) => {
    setSelected(summary);
    setDeck(null);
    setDeckError(null);
    setIndex(0);
    setResults({});

    if (!hasBackend) {
      setDeck(demoDecks[summary.deckId] ?? null);
      return;
    }

    try {
      setDeck(await fetchDeck(summary.deckId));
    } catch (error) {
      setDeckError(error.message);
    }
  }, []);

  const backToCatalog = useCallback(() => {
    setSelected(null);
    setDeck(null);
    setDeckError(null);
  }, []);

  const handleAnswered = useCallback(({ questionId, isCorrect }) => {
    setResults((prev) => ({ ...prev, [questionId]: isCorrect }));
  }, []);

  // --- Derivados --------------------------------------------------------
  const score = useMemo(() => {
    const values = Object.values(results);
    return { answered: values.length, correct: values.filter(Boolean).length };
  }, [results]);

  const totalQuestions = useMemo(
    () => (catalog ?? []).reduce((sum, d) => sum + (d.questionCount ?? 0), 0),
    [catalog],
  );

  const question = deck?.questions[index];
  const heading = selected?.title ?? APP_TITLE;

  const subtitle = selected
    ? score.answered > 0
      ? `${score.correct} de ${score.answered} correctas`
      : `${selected.questionCount} ${selected.questionCount === 1 ? "pregunta" : "preguntas"}`
    : catalog
      ? `${catalog.length} ${catalog.length === 1 ? "mazo" : "mazos"} · ${totalQuestions} preguntas`
      : "Cargando…";

  return (
    <main className="min-h-screen bg-aws-mist bg-grid px-4 py-10 transition-colors dark:bg-aws-ink">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
        <header className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            {selected && (
              <button
                type="button"
                onClick={backToCatalog}
                className="mb-2 rounded-lg text-sm text-aws-muted transition-colors hover:text-aws-blue focus:outline-none focus-visible:ring-2 focus-visible:ring-aws-blue"
              >
                ← Todos los mazos
              </button>
            )}

            {/* La `key` hace que el titulo se anime al cambiar de pantalla. */}
            <AnimatePresence mode="wait">
              <motion.h1
                key={heading}
                initial={{ opacity: 0, y: -6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 6 }}
                transition={{ duration: 0.2 }}
                className="truncate text-2xl font-bold text-aws-ink dark:text-aws-white"
              >
                {heading}
              </motion.h1>
            </AnimatePresence>

            <p className="mt-1 flex items-center gap-2 text-sm text-aws-muted">
              {selected && (
                <span className="rounded-full bg-aws-blue px-2 py-0.5 text-xs font-medium text-aws-ink">
                  {selected.category}
                </span>
              )}
              {subtitle}
              {!hasBackend && " · demo sin backend"}
            </p>
          </div>

          <button
            type="button"
            onClick={toggleDark}
            aria-label="Alternar modo oscuro"
            className="shrink-0 rounded-lg border border-aws-mist-line px-3 py-2 text-sm text-aws-ink transition-colors hover:border-aws-blue focus:outline-none focus-visible:ring-2 focus-visible:ring-aws-blue dark:border-aws-line dark:text-aws-white"
          >
            {isDark ? "☀︎" : "☾"}
          </button>
        </header>

        {/* --- Pantalla principal: catalogo ------------------------------ */}
        {!selected && (
          <DeckPicker
            decks={catalog ?? []}
            onSelect={openDeck}
            isLoading={catalog === null && !catalogError}
            error={catalogError}
          />
        )}

        {/* --- Pantalla de estudio -------------------------------------- */}
        {selected && deckError && (
          <p className="rounded-2xl border-2 border-aws-magenta bg-aws-white p-5 text-sm text-aws-ink dark:bg-aws-surface dark:text-aws-white">
            {deckError}
          </p>
        )}

        {selected && !deck && !deckError && (
          <p className="py-12 text-center text-sm text-aws-muted">
            Cargando preguntas…
          </p>
        )}

        {question && (
          <div className="flex flex-col items-center gap-6">
            {/* La `key` fuerza el remontaje al cambiar de pregunta: reinicia
                el estado interno de giro sin exponerlo como prop. */}
            <Flashcard
              key={question.questionId}
              question={question}
              onAnswered={handleAnswered}
            />

            <nav className="flex w-full max-w-2xl items-center justify-between">
              <button
                type="button"
                onClick={() => setIndex((i) => Math.max(0, i - 1))}
                disabled={index === 0}
                className="rounded-lg px-3 py-2 text-sm text-aws-muted transition-colors enabled:hover:text-aws-blue disabled:opacity-40 focus:outline-none focus-visible:ring-2 focus-visible:ring-aws-blue"
              >
                ← Anterior
              </button>

              <span className="font-mono text-xs tabular-nums text-aws-muted">
                {index + 1} / {deck.questions.length}
              </span>

              <button
                type="button"
                onClick={() =>
                  setIndex((i) => Math.min(deck.questions.length - 1, i + 1))
                }
                disabled={index === deck.questions.length - 1}
                className="rounded-lg px-3 py-2 text-sm text-aws-muted transition-colors enabled:hover:text-aws-blue disabled:opacity-40 focus:outline-none focus-visible:ring-2 focus-visible:ring-aws-blue"
              >
                Siguiente →
              </button>
            </nav>
          </div>
        )}
      </div>
    </main>
  );
}
