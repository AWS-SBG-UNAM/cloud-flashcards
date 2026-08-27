import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import DeckPicker from "./DeckPicker.jsx";

const decks = [
  { deckId: "indices", title: "Indices B-Tree", category: "Bases de Datos", questionCount: 12 },
  { deckId: "acid", title: "Transacciones ACID", category: "Bases de Datos", questionCount: 5 },
  { deckId: "iam", title: "IAM basico", category: "Seguridad", questionCount: 1 },
];

describe("DeckPicker", () => {
  it("agrupa los mazos por tematica", () => {
    render(<DeckPicker decks={decks} onSelect={() => {}} />);

    const bd = screen.getByRole("heading", { name: /Bases de Datos/ });
    const seg = screen.getByRole("heading", { name: /Seguridad/ });

    expect(bd).toBeInTheDocument();
    expect(seg).toBeInTheDocument();
    // El contador de cada grupo refleja cuantos mazos contiene.
    expect(bd).toHaveTextContent("(2)");
    expect(seg).toHaveTextContent("(1)");
  });

  it("muestra el numero de preguntas y singulariza correctamente", () => {
    render(<DeckPicker decks={decks} onSelect={() => {}} />);

    expect(screen.getByText("12 preguntas")).toBeInTheDocument();
    expect(screen.getByText("1 pregunta")).toBeInTheDocument();
  });

  it("devuelve el mazo elegido al pulsarlo", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<DeckPicker decks={decks} onSelect={onSelect} />);

    await user.click(screen.getByRole("button", { name: /Indices B-Tree/ }));

    expect(onSelect).toHaveBeenCalledWith(decks[0]);
  });

  it("asigna el mismo color a una tematica de forma estable", () => {
    const { container, unmount } = render(<DeckPicker decks={decks} onSelect={() => {}} />);
    const primero = container.querySelector("h2 span").className;
    unmount();

    const segundo = render(<DeckPicker decks={decks} onSelect={() => {}} />)
      .container.querySelector("h2 span").className;

    expect(primero).toBe(segundo);
    expect(primero).toMatch(/bg-aws-/);
  });

  it("invita a subir un .md cuando no hay mazos", () => {
    render(<DeckPicker decks={[]} onSelect={() => {}} />);

    expect(screen.getByText(/Todavia no hay mazos/)).toBeInTheDocument();
    expect(screen.getByText(/carpeta de primer nivel/)).toBeInTheDocument();
  });

  it("muestra el estado de carga", () => {
    render(<DeckPicker decks={[]} onSelect={() => {}} isLoading />);

    expect(screen.getByText(/Cargando mazos/)).toBeInTheDocument();
  });

  it("muestra el error sin pintar el catalogo", () => {
    render(<DeckPicker decks={decks} onSelect={() => {}} error="El API respondio 500." />);

    expect(screen.getByText("El API respondio 500.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Indices/ })).not.toBeInTheDocument();
  });
});
