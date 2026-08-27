/**
 * Cliente del REST API.
 *
 * Contrato servido por backend/api/app.py:
 *   GET /decks            -> { count, decks[] }
 *   GET /decks/{deckId}   -> { deckId, title, category, count, questions[] }
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ?? "";

/** Indica si hay backend configurado; si no, la app usa los datos de demo. */
export const hasBackend = Boolean(BASE_URL);

async function request(path, { signal } = {}) {
  if (!hasBackend) {
    throw new Error("VITE_API_BASE_URL no esta configurada.");
  }

  const response = await fetch(`${BASE_URL}${path}`, { signal });

  if (response.status === 404) {
    const error = new Error("No encontrado.");
    error.status = 404;
    throw error;
  }
  if (!response.ok) {
    throw new Error(`El API respondio ${response.status}.`);
  }

  return response.json();
}

/** Catálogo completo para la pantalla principal. */
export async function fetchDecks(options) {
  const { decks } = await request("/decks", options);
  return decks;
}

/** Preguntas de un mazo concreto. */
export async function fetchDeck(deckId, options) {
  try {
    return await request(`/decks/${encodeURIComponent(deckId)}`, options);
  } catch (error) {
    if (error.status === 404) {
      throw new Error(`El mazo "${deckId}" no existe todavia.`);
    }
    throw error;
  }
}
