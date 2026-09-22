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
}
