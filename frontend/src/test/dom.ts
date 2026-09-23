/** Browser APIs jsdom does not implement, which Radix primitives expect. */
export function installDomStubs(): void {
  if (!("ResizeObserver" in globalThis)) {
    globalThis.ResizeObserver = class {
      readonly observe = () => undefined;
      readonly unobserve = () => undefined;
      readonly disconnect = () => undefined;
    };
  }
  const element = globalThis.Element.prototype as unknown as Record<string, unknown>;
  element.hasPointerCapture ??= () => false;
  element.setPointerCapture ??= () => undefined;
  element.releasePointerCapture ??= () => undefined;
  element.scrollIntoView ??= () => undefined;
  installLayout();
}

const VIEWPORT = { width: 1024, height: 768 };
let layoutStubbed = false;

/**
 * jsdom never lays anything out, so every element is 0×0 — and a virtualised list whose
 * viewport is zero pixels tall renders no rows at all. Give elements a window-sized box,
 * which is what the virtualiser measures to decide how much to fill.
 */
function installLayout(): void {
  if (layoutStubbed) return;
  layoutStubbed = true;
  for (const [name, size] of [
    ["offsetWidth", VIEWPORT.width],
    ["offsetHeight", VIEWPORT.height],
  ] as const) {
    Object.defineProperty(globalThis.HTMLElement.prototype, name, {
      configurable: true,
      get: () => size,
    });
  }
}
