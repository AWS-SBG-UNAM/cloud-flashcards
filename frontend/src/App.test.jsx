import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./api/decks.js", () => ({
  hasBackend: true,
  fetchDecks: vi.fn(),
  fetchDeck: vi.fn(),
}));

import App from "./App.jsx";
import { fetchDeck, fetchDecks } from "./api/decks.js";

const catalogo = [
  { deckId: "aws", title: "Fundamentos de AWS", category: "General", questionCount: 3 },
  { deckId: "iam", title: "IAM basico", category: "Seguridad", questionCount: 4 },
];

const pregunta = (n) => ({
  questionId: `q${n}`,
  position: n - 1,
  prompt: `Pregunta ${n}`,
  options: [
    { text: `mal-${n}`, isCorrect: false },
    { text: `bien-${n}`, isCorrect: true },
  ],
  explanation: `Explicacion ${n}`,
});

const mazo = {
  deckId: "aws",
  title: "Fundamentos de AWS",
  category: "General",
  count: 3,
  questions: [pregunta(1), pregunta(2), pregunta(3)],
};

/** Abre el mazo "Fundamentos de AWS" desde el catalogo. */
async function abrirMazo(user) {
  await user.click(await screen.findByRole("button", { name: /Fundamentos de AWS/ }));
  await screen.findByText("Pregunta 1");
}

beforeEach(() => {
  vi.clearAllMocks();
  fetchDecks.mockResolvedValue(catalogo);
  fetchDeck.mockResolvedValue(mazo);
});

describe("pantalla principal", () => {
  it("lista el catalogo agrupado y resume la coleccion", async () => {
    render(<App />);

    expect(await screen.findByText("2 mazos · 7 preguntas")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Bases|General/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Cloud Flashcards");
  });

  it("propaga el error del catalogo sin romper la pantalla", async () => {
    fetchDecks.mockRejectedValue(new Error("El API respondio 500."));
    render(<App />);

    expect(await screen.findByText("El API respondio 500.")).toBeInTheDocument();
  });
});

describe("cambio de titulo al cargar un mazo", () => {
  it("sustituye el titulo de la app por el del mazo", async () => {
    const user = userEvent.setup();
    render(<App />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Cloud Flashcards");
    await abrirMazo(user);

    // `AnimatePresence mode="wait"` mantiene el titulo anterior durante su
    // animacion de salida (~200 ms), asi que se espera al estado final.
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
        "Fundamentos de AWS",
      ),
    );
    expect(screen.getByText("General")).toBeInTheDocument();
  });

  it("sincroniza tambien el titulo de la pestana", async () => {
    const user = userEvent.setup();
    render(<App />);

    await waitFor(() => expect(document.title).toBe("Cloud Flashcards"));
    await abrirMazo(user);

    await waitFor(() =>
      expect(document.title).toBe("Fundamentos de AWS · Cloud Flashcards"),
    );
  });

  it("vuelve al catalogo y restaura el titulo", async () => {
    const user = userEvent.setup();
    render(<App />);
    await abrirMazo(user);

    await user.click(screen.getByRole("button", { name: /Todos los mazos/ }));

    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
        "Cloud Flashcards",
      ),
    );
    await waitFor(() => expect(document.title).toBe("Cloud Flashcards"));
  });
});

describe("marcador", () => {
  it("cuenta una respuesta por pregunta", async () => {
    const user = userEvent.setup();
    render(<App />);
    await abrirMazo(user);

    await user.click(screen.getByRole("button", { name: "bien-1" }));
    expect(await screen.findByText("1 de 1 correctas")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Siguiente/ }));
    await user.click(await screen.findByRole("button", { name: "mal-2" }));
    expect(await screen.findByText("1 de 2 correctas")).toBeInTheDocument();
  });

  it("reintentar SUSTITUYE el resultado, no anade otra respuesta", async () => {
    // Regresion del bug reportado: fallar la 3 de 3 y reintentarla mostraba
    // 3/4, luego 4/5... porque cada intento incrementaba el total.
    const user = userEvent.setup();
    render(<App />);
    await abrirMazo(user);

    await user.click(screen.getByRole("button", { name: "mal-1" }));
    expect(await screen.findByText("0 de 1 correctas")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Intentar de nuevo/ }));
    await user.click(await screen.findByRole("button", { name: "bien-1" }));

    expect(await screen.findByText("1 de 1 correctas")).toBeInTheDocument();
    expect(screen.queryByText("1 de 2 correctas")).not.toBeInTheDocument();
  });

  it("no acumula al reintentar varias veces", async () => {
    const user = userEvent.setup();
    render(<App />);
    await abrirMazo(user);

    for (const opcion of ["mal-1", "bien-1", "mal-1"]) {
      await user.click(await screen.findByRole("button", { name: opcion }));
      const reintentar = screen.queryByRole("button", { name: /Intentar de nuevo/ });
      if (reintentar) await user.click(reintentar);
    }

    expect(await screen.findByText("0 de 1 correctas")).toBeInTheDocument();
  });

  it("se reinicia al abrir otro mazo", async () => {
    const user = userEvent.setup();
    render(<App />);
    await abrirMazo(user);

    await user.click(screen.getByRole("button", { name: "bien-1" }));
    expect(await screen.findByText("1 de 1 correctas")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Todos los mazos/ }));
    fetchDeck.mockResolvedValue({ ...mazo, deckId: "iam", title: "IAM basico" });
    await user.click(screen.getByRole("button", { name: /IAM basico/ }));

    expect(await screen.findByText(/preguntas$/)).toBeInTheDocument();
    expect(screen.queryByText(/correctas/)).not.toBeInTheDocument();
  });
});
