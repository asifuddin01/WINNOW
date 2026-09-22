import type {
  CriterionKind,
  KeywordKind,
  ProjectRole,
  ProjectStatus,
  ReasonStage,
  ReviewType,
  ScreeningStage,
} from "@/api/projects";

export const REVIEW_TYPES: Record<ReviewType, string> = {
  systematic: "Systematic review",
  scoping: "Scoping review",
  rapid: "Rapid review",
  umbrella: "Umbrella review",
  other: "Other",
};

export const STATUSES: Record<ProjectStatus, string> = {
  setup: "Setting up",
  screening: "Title and abstract screening",
  fulltext: "Full-text screening",
  extraction: "Data extraction",
  complete: "Complete",
  archived: "Archived",
};

export const ROLES: Record<ProjectRole, string> = {
  owner: "Owner",
  admin: "Admin",
  reviewer: "Reviewer",
  viewer: "Viewer",
};

export const ROLE_DESCRIPTIONS: Record<ProjectRole, string> = {
  owner: "Everything, including deleting the review or handing it on.",
  admin: "Runs the review: setup, imports, the team and settings.",
  reviewer: "Screens records and reads the review.",
  viewer: "Reads the review and exports; changes nothing.",
};

export const CRITERION_KINDS: Record<CriterionKind, string> = {
  inclusion: "Include",
  exclusion: "Exclude",
};

export const KEYWORD_KINDS: Record<KeywordKind, string> = {
  include: "Suggests including",
  exclude: "Suggests excluding",
  neutral: "Just highlight",
};

export const REASON_STAGES: Record<ReasonStage, string> = {
  title_abstract: "Title and abstract",
  full_text: "Full text",
  both: "Both stages",
};

export const SCREENING_STAGES: Record<ScreeningStage, string> = {
  title_abstract: "Title and abstract",
  full_text: "Full text",
};
