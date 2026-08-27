import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import Flashcard from "./Flashcard.jsx";

const question = {
  questionId: "q1",
  prompt: "¿Que clave permite leer un mazo con un solo Query?",
  options: [
    { text: "Un Scan filtrando por deckId", isCorrect: false },
    { text: "deckId como Partition Key", isCorrect: true },
  ],
  explanation: "Los items con la misma Partition Key viven en una particion.",
};

/** [anverso, reverso] — ambas caras existen siempre; el giro las alterna. */
const faces = (container) => [...container.querySelectorAll("section")];

describe("Flashcard", () => {
  it("muestra el enunciado y un boton por opcion", () => {
    render(<Flashcard question={question} />);

    expect(screen.getByText(question.prompt)).toBeInTheDocument();
    question.options.forEach((option) => {
      expect(screen.getByRole("button", { name: option.text })).toBeInTheDocument();
    });
  });

  it("arranca sin girar: el reverso esta oculto a la accesibilidad", () => {
    const { container } = render(<Flashcard question={question} />);
    const [front, back] = faces(container);

    expect(front).toHaveAttribute("aria-hidden", "false");
    expect(back).toHaveAttribute("aria-hidden", "true");
  });

  it("aplica la perspectiva y el contexto 3D que necesita el giro", () => {
    const { container } = render(<Flashcard question={question} />);

    expect(container.firstChild).toHaveStyle({ perspective: "1200px" });
    expect(container.querySelector("[style*='preserve-3d']")).not.toBeNull();
  });

  it("gira y marca el acierto al elegir la opcion correcta", async () => {
    const user = userEvent.setup();
    const { container } = render(<Flashcard question={question} />);

    await user.click(screen.getByRole("button", { name: "deckId como Partition Key" }));
    const [front, back] = faces(container);

    expect(back).toHaveAttribute("aria-hidden", "false");
    expect(front).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByText("¡Correcto!")).toBeInTheDocument();
    expect(back.className).toMatch(/aws-mint/); // Mint 400, marca AWS
  });

  it("gira, marca el fallo y revela la respuesta correcta", async () => {
    const user = userEvent.setup();
    const { container } = render(<Flashcard question={question} />);

    await user.click(screen.getByRole("button", { name: "Un Scan filtrando por deckId" }));
    const [, back] = faces(container);

    expect(screen.getByText("Incorrecto")).toBeInTheDocument();
    expect(back.className).toMatch(/aws-magenta/); // Magenta 400, marca AWS
    // Acotado al reverso: el texto tambien existe como boton en el anverso.
    expect(within(back).getByText("deckId como Partition Key")).toBeInTheDocument();
    expect(within(back).getByText(/Respuesta correcta/)).toBeInTheDocument();
  });

  it("muestra la explicacion en el reverso", async () => {
    const user = userEvent.setup();
    render(<Flashcard question={question} />);

    await user.click(screen.getByRole("button", { name: "deckId como Partition Key" }));

    expect(screen.getByText(question.explanation)).toBeInTheDocument();
  });

  it("notifica el resultado al componente padre", async () => {
    const user = userEvent.setup();
    const onAnswered = vi.fn();
    render(<Flashcard question={question} onAnswered={onAnswered} />);

    await user.click(screen.getByRole("button", { name: "deckId como Partition Key" }));

    expect(onAnswered).toHaveBeenCalledTimes(1);
    expect(onAnswered).toHaveBeenCalledWith({
      questionId: "q1",
      isCorrect: true,
      selectedText: "deckId como Partition Key",
    });
  });

  it("bloquea el anverso tras responder para impedir cambiar la eleccion", async () => {
    const user = userEvent.setup();
    const { container } = render(<Flashcard question={question} />);

    await user.click(screen.getByRole("button", { name: "deckId como Partition Key" }));
    const [front] = faces(container);

    expect(front).toHaveStyle({ pointerEvents: "none" });
  });

  it("permite reintentar y vuelve al anverso", async () => {
    const user = userEvent.setup();
    const { container } = render(<Flashcard question={question} />);

    await user.click(screen.getByRole("button", { name: "deckId como Partition Key" }));
    await user.click(screen.getByRole("button", { name: /Intentar de nuevo/ }));
    const [front, back] = faces(container);

    expect(front).toHaveAttribute("aria-hidden", "false");
    expect(back).toHaveAttribute("aria-hidden", "true");
  });

  it("no rompe si la pregunta llega sin opciones", () => {
    const vacia = { questionId: "q2", prompt: "Sin opciones", options: [], explanation: "" };

    expect(() => render(<Flashcard question={vacia} />)).not.toThrow();
  });
});
