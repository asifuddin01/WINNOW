import { useTranslation } from "react-i18next";
/** First focusable element on every page: jumps keyboard users past the navigation. */
export function SkipLink() {
  const { t } = useTranslation();
  return (
    <a
      href="#main"
      className="sr-only z-50 rounded-md bg-background px-4 py-2 text-sm font-medium text-foreground shadow-md ring-2 ring-ring focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
    >
      {t("shell.skip")}
    </a>
  );
}
