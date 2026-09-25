import type { Notice } from "@/api/notifications";

/** A notice in words, and where it leads (null: nowhere to go in Winnow). */
export function describeNotice(notice: Notice): { text: string; to: string | null } {
  const data = notice.data as Record<string, string | number | undefined>;
  const review = String(data.project_title ?? "a review");
  const who = String(data.by ?? "Someone");
  const pid = notice.project_id;
  switch (notice.kind) {
    case "conflicts":
      return {
        text: `${notice.count} new ${notice.count === 1 ? "conflict" : "conflicts"} to resolve in ${review}`,
        to: pid ? `/p/${pid}/conflicts` : null,
      };
    case "invite":
      return {
        text: `${who} invited you to ${review}. Accept from the invitation email.`,
        to: null,
      };
    case "mention":
      return {
        text: `${who} mentioned you in ${review}: “${String(data.excerpt ?? "")}”`,
        to: pid && data.record_id ? `/p/${pid}/records?record=${String(data.record_id)}` : null,
      };
    case "import_finished":
      return {
        text: `Your import of ${String(data.filename ?? "a file")} into ${review} finished: ${Number(data.imported ?? 0).toLocaleString()} records`,
        to: pid ? `/p/${pid}/import` : null,
      };
    case "import_failed":
      return {
        text: `Your import of ${String(data.filename ?? "a file")} into ${review} failed`,
        to: pid ? `/p/${pid}/import` : null,
      };
  }
}
