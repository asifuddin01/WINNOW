import { queryOptions } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";
import type { components } from "@/api/schema";

export type ExtractionForm = components["schemas"]["FormOut"];
export type EntryOut = components["schemas"]["EntryOut"];
export type RecordExtraction = components["schemas"]["RecordExtraction"];
export type ConsensusView = components["schemas"]["ConsensusView"];
export type StudyExtraction = components["schemas"]["StudyExtraction"];

/** The form schema as `app.extraction` reads and writes it. */
export type FieldType =
  | "short_text"
  | "long_text"
  | "number"
  | "select"
  | "multi_select"
  | "yes_no_unclear"
  | "date"
  | "table"
  | "section";

export interface FieldDef {
  key: string;
  label: string;
  type: FieldType;
  help?: string;
  required?: boolean;
  options?: string[];
  unit?: string;
  integer?: boolean;
  minimum?: number;
  maximum?: number;
  columns?: FieldDef[];
  min_rows?: number;
  max_rows?: number;
}

export interface FormSchema {
  fields: FieldDef[];
}

export type Row = Record<string, unknown>;
export type EntryData = Record<string, unknown>;

export const schemaOf = (form: ExtractionForm): FormSchema =>
  (form.schema as unknown as FormSchema | undefined) ?? { fields: [] };

export const extractionKeys = {
  all: (pid: string) => ["projects", pid, "extraction"] as const,
  forms: (pid: string) => ["projects", pid, "extraction", "forms"] as const,
  studies: (pid: string, fid: string) => ["projects", pid, "extraction", "studies", fid] as const,
  record: (pid: string, fid: string, rid: string) =>
    ["projects", pid, "extraction", "record", fid, rid] as const,
  consensus: (pid: string, fid: string, rid: string) =>
    ["projects", pid, "extraction", "consensus", fid, rid] as const,
};

export const formsQuery = (pid: string) =>
  queryOptions({
    queryKey: extractionKeys.forms(pid),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/extraction-forms", {
          signal,
          params: { path: { pid } },
        }),
      ),
  });

export const studiesQuery = (pid: string, fid: string) =>
  queryOptions({
    queryKey: extractionKeys.studies(pid, fid),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/extraction-forms/{fid}/studies", {
          signal,
          params: { path: { pid, fid } },
        }),
      ),
  });

export const recordExtractionQuery = (pid: string, fid: string, rid: string) =>
  queryOptions({
    queryKey: extractionKeys.record(pid, fid, rid),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/extraction-forms/{fid}/entries/{rid}", {
          signal,
          params: { path: { pid, fid, rid } },
        }),
      ),
  });

export const consensusQuery = (pid: string, fid: string, rid: string) =>
  queryOptions({
    queryKey: extractionKeys.consensus(pid, fid, rid),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/extraction-forms/{fid}/consensus/{rid}", {
          signal,
          params: { path: { pid, fid, rid } },
        }),
      ),
  });

export async function createForm(pid: string, name: string, dual: boolean) {
  return unwrap(
    await api.POST("/api/v1/projects/{pid}/extraction-forms", {
      params: { path: { pid } },
      body: { name, dual, schema: { fields: [] } },
    }),
  );
}

export async function updateForm(
  pid: string,
  fid: string,
  body: { name?: string; dual?: boolean; schema?: FormSchema },
) {
  return unwrap(
    await api.PATCH("/api/v1/projects/{pid}/extraction-forms/{fid}", {
      params: { path: { pid, fid } },
      body: body as never,
    }),
  );
}

export async function publishForm(pid: string, fid: string) {
  return unwrap(
    await api.POST("/api/v1/projects/{pid}/extraction-forms/{fid}/publish", {
      params: { path: { pid, fid } },
    }),
  );
}

export async function newVersion(pid: string, fid: string) {
  return unwrap(
    await api.POST("/api/v1/projects/{pid}/extraction-forms/{fid}/versions", {
      params: { path: { pid, fid } },
    }),
  );
}

export async function deleteForm(pid: string, fid: string): Promise<void> {
  unwrap(
    await api.DELETE("/api/v1/projects/{pid}/extraction-forms/{fid}", {
      params: { path: { pid, fid } },
    }),
  );
}

export async function saveEntry(
  pid: string,
  fid: string,
  rid: string,
  data: EntryData,
  status: "draft" | "submitted",
) {
  return unwrap(
    await api.PUT("/api/v1/projects/{pid}/extraction-forms/{fid}/entries/{rid}", {
      params: { path: { pid, fid, rid } },
      body: { data, status },
    }),
  );
}

export async function saveConsensus(pid: string, fid: string, rid: string, data: EntryData) {
  return unwrap(
    await api.PUT("/api/v1/projects/{pid}/extraction-forms/{fid}/consensus/{rid}", {
      params: { path: { pid, fid, rid } },
      body: { data },
    }),
  );
}
