/**
 * The global footer (guide 19.2). Required on every page, including sign-in and error
 * pages; it sits below the content and is never fixed, so it cannot cover controls.
 * Never remove it.
 */
export function Footer() {
  return (
    <footer className="border-t border-border py-4 text-center text-sm text-muted-foreground">
      <span>
        Winnow · Built by{" "}
        <a
          href="https://asifuddin.com"
          target="_blank"
          rel="noopener noreferrer"
          className="font-medium text-foreground underline-offset-4 hover:underline focus-visible:outline-2"
        >
          Asif
        </a>
      </span>
    </footer>
  );
}
