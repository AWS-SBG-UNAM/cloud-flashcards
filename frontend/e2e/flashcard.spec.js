import { expect, test } from "@playwright/test";

/**
 * End-to-end contra el API REAL desplegado en AWS (mx-central-1).
 *
 * A diferencia de los tests de Vitest, que montan los componentes con datos
 * fijos, esto ejerce la cadena completa desde el navegador:
 *   fetch del DOM -> CORS -> API Gateway -> Lambda -> DynamoDB
 */

const SHOTS = "e2e/.artifacts";

/** Recolecta errores de consola y peticiones fallidas (donde asoma el CORS).
 *
 * Se descarta un `net::ERR_ABORTED` sobre /decks: en desarrollo React 19
 * ejecuta StrictMode, que monta -> desmonta -> remonta cada componente. El
 * `AbortController` del useEffect cancela el primer fetch, que es exactamente
 * lo que debe hacer para no actualizar estado de un componente desmontado.
 * En el build de produccion no ocurre, porque no hay doble montaje.
 */
function watchFailures(page) {
  const failures = [];
  const esAbortoDeStrictMode = (r) =>
    r.failure()?.errorText === "net::ERR_ABORTED" && r.url().includes("/decks");

  page.on("console", (m) => m.type() === "error" && failures.push(`console: ${m.text()}`));
  page.on("pageerror", (e) => failures.push(`pageerror: ${e.message}`));
  page.on("requestfailed", (r) => {
    if (!esAbortoDeStrictMode(r)) {
      failures.push(`requestfailed: ${r.url()} — ${r.failure()?.errorText}`);
    }
  });
  return failures;
}

const h1 = (page) => page.getByRole("heading", { level: 1 });

test("catalogo, estudio de un mazo y cambio de tema", async ({ page }) => {
  const failures = watchFailures(page);

  const catalogResponse = page.waitForResponse(
    (r) => r.url().includes("execute-api") && r.url().endsWith("/decks"),
  );

  await page.goto("/");
  const response = await catalogResponse;

  // --- 1. El catalogo llega desde AWS y pasa el CORS ---------------------
  expect(response.status()).toBe(200);
  expect(response.url()).toContain("mx-central-1");
  expect(response.headers()["access-control-allow-origin"]).toBe("*");

  const { decks } = await response.json();
  expect(decks.length).toBeGreaterThanOrEqual(4);

  // --- 2. La pantalla principal agrupa por tematica ----------------------
  await expect(h1(page)).toHaveText("Cloud Flashcards");
  for (const categoria of ["Bases de Datos", "Seguridad", "Serverless"]) {
    await expect(page.getByRole("heading", { name: new RegExp(categoria) })).toBeVisible();
  }
  await expect(page.getByRole("button", { name: /Indices B-Tree/ })).toBeVisible();

  // Cada tematica recibe un acento distinto de la paleta de marca.
  const puntos = await page.locator("h2 span[class*='bg-aws-']").evaluateAll(
    (nodes) => nodes.map((n) => n.className),
  );
  expect(new Set(puntos).size).toBe(puntos.length);

  // --- 3. La escala global es +20% --------------------------------------
  const rootFontSize = await page.evaluate(
    () => getComputedStyle(document.documentElement).fontSize,
  );
  expect(rootFontSize).toBe("19.2px"); // 16px x 1,2

  // La entrada de los grupos va escalonada (60 ms por grupo): sin esperar,
  // la captura sale con los ultimos a medio aparecer.
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${SHOTS}/1-catalogo-oscuro.png`, fullPage: true });

  // --- 4. Abrir un mazo cambia el titulo de pantalla y de pestana --------
  await page.getByRole("button", { name: /Indices B-Tree/ }).click();

  await expect(h1(page)).toHaveText("Indices B-Tree");
  await expect(page.getByText("Bases de Datos", { exact: true })).toBeVisible();
  await expect(page).toHaveTitle("Indices B-Tree · Cloud Flashcards");
  await expect(page.getByText("1 / 3")).toBeVisible();

  await page.screenshot({ path: `${SHOTS}/2-mazo-anverso.png`, fullPage: true });

  // --- 5. Fallar gira la tarjeta y marca 0 de 1 -------------------------
  await page.getByRole("button", { name: /O\(n\), hay que recorrer/ }).click();

  await expect(page.getByText("Incorrecto")).toBeVisible();
  await expect(page.getByText("0 de 1 correctas")).toBeVisible();
  await expect(
    page.getByText(/La altura del arbol crece de forma logaritmica/),
  ).toBeVisible();

  const caras = page.locator("section");
  await expect(caras.nth(1)).toHaveAttribute("aria-hidden", "false");

  await page.waitForTimeout(700); // deja terminar la animación de giro
  await page.screenshot({ path: `${SHOTS}/3-reverso-incorrecto.png`, fullPage: true });

  // --- 6. REGRESION: reintentar sustituye, no acumula -------------------
  await page.getByRole("button", { name: /Intentar de nuevo/ }).click();
  await page.getByRole("button", { name: "O(log n)" }).click();

  await expect(page.getByText("¡Correcto!")).toBeVisible();
  await expect(page.getByText("1 de 1 correctas")).toBeVisible();
  await expect(page.getByText("1 de 2 correctas")).toHaveCount(0);

  await page.waitForTimeout(700);
  await page.screenshot({ path: `${SHOTS}/4-reverso-correcto.png`, fullPage: true });

  // --- 7. Volver al catalogo restaura el titulo -------------------------
  await page.getByRole("button", { name: /Todos los mazos/ }).click();
  await expect(h1(page)).toHaveText("Cloud Flashcards");
  await expect(page).toHaveTitle("Cloud Flashcards");

  // --- 8. Modo claro ----------------------------------------------------
  await expect(page.locator("html")).toHaveClass(/dark/);
  await page.getByRole("button", { name: "Alternar modo oscuro" }).click();
  await expect(page.locator("html")).not.toHaveClass(/dark/);

  await page.waitForTimeout(300);
  await page.screenshot({ path: `${SHOTS}/5-catalogo-claro.png`, fullPage: true });

  // --- 9. Nada roto por el camino ---------------------------------------
  expect(failures).toEqual([]);
});

test("el marcador se reinicia al cambiar de mazo", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: /IAM basico/ }).click();
  await page.getByRole("button", { name: /Nada: IAM deniega/ }).click();
  await expect(page.getByText("1 de 1 correctas")).toBeVisible();

  await page.getByRole("button", { name: /Todos los mazos/ }).click();
  await page.getByRole("button", { name: /Transacciones ACID/ }).click();

  await expect(page.getByText(/correctas/)).toHaveCount(0);
  await expect(page.getByText("2 preguntas")).toBeVisible();
});

test("un mazo inexistente muestra el error sin romper la app", async ({ page }) => {
  await page.route("**/decks/*", (route) =>
    route.fulfill({
      status: 404,
      headers: { "access-control-allow-origin": "*", "content-type": "application/json" },
      body: JSON.stringify({ message: "No existe el mazo 'x'." }),
    }),
  );

  await page.goto("/");
  await page.getByRole("button", { name: /Indices B-Tree/ }).click();

  await expect(page.getByText(/no existe todavia/i)).toBeVisible();
});
