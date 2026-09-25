import type { Notice } from "@/api/notifications";
import i18n from "@/i18n";

/** A notice in words, and where it leads (null: nowhere to go in Winnow). */
export function describeNotice(notice: Notice): { text: string; to: string | null } {
  const { t } = i18n;
  const data = notice.data as Record<string, string | number | undefined>;
  const review = String(data.project_title ?? t("notices.aReview"));
  const who = String(data.by ?? t("notices.someone"));
  const file = String(data.filename ?? t("notices.aFile"));
  const pid = notice.project_id;
  switch (notice.kind) {
    case "conflicts":
      return {
        text: t("notices.conflicts", { count: notice.count, review }),
        to: pid ? `/p/${pid}/conflicts` : null,
      };
    case "invite":
      return { text: t("notices.invite", { who, review }), to: null };
    case "mention":
      return {
        text: t("notices.mention", { who, review, excerpt: String(data.excerpt ?? "") }),
        to: pid && data.record_id ? `/p/${pid}/records?record=${String(data.record_id)}` : null,
      };
    case "import_finished":
      return {
        text: t("notices.importFinished", { file, review, count: Number(data.imported ?? 0) }),
        to: pid ? `/p/${pid}/import` : null,
      };
    case "import_failed":
      return {
        text: t("notices.importFailed", { file, review }),
        to: pid ? `/p/${pid}/import` : null,
      };
  }
}
