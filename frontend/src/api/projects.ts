import { queryOptions, type QueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";
import type { components } from "@/api/schema";

export type Project = components["schemas"]["ProjectOut"];
export type ProjectSummary = components["schemas"]["ProjectSummary"];
export type ProjectSettings = components["schemas"]["ProjectSettings"];
export type ProjectSettingsPatch = components["schemas"]["ProjectSettingsPatch"];
export type ProjectCreate = components["schemas"]["ProjectCreate"];
export type ProjectUpdate = components["schemas"]["ProjectUpdate"];
export type ReviewType = components["schemas"]["ReviewType"];
export type ProjectStatus = components["schemas"]["ProjectStatus"];
export type ProjectRole = components["schemas"]["ProjectRole"];
export type Capability = components["schemas"]["Capability"];
export type Member = components["schemas"]["MemberOut"];
export type Invite = components["schemas"]["InviteOut"];
export type NewInvite = components["schemas"]["InviteCreated"];
export type InvitePreview = components["schemas"]["InvitePreview"];
export type Criterion = components["schemas"]["CriterionOut"];
export type CriterionKind = components["schemas"]["CriterionKind"];
export type KeywordGroup = components["schemas"]["KeywordGroupOut"];
export type Keyword = components["schemas"]["KeywordOut"];
export type KeywordKind = components["schemas"]["KeywordKind"];
export type Reason = components["schemas"]["ReasonOut"];
export type ReasonStage = components["schemas"]["ReasonStage"];
export type Label = components["schemas"]["LabelOut"];
export type Color = NonNullable<components["schemas"]["LabelCreate"]["color"]>;
export type ScreeningStage = components["schemas"]["ScreeningStage"];
export type AssignableRole = NonNullable<components["schemas"]["InviteCreate"]["role"]>;

export const projectKeys = {
  all: ["projects"] as const,
  list: ["projects", "list"] as const,
  detail: (pid: string) => ["projects", pid] as const,
  members: (pid: string) => ["projects", pid, "members"] as const,
  invites: (pid: string) => ["projects", pid, "invites"] as const,
  criteria: (pid: string) => ["projects", pid, "criteria"] as const,
  keywords: (pid: string) => ["projects", pid, "keyword-groups"] as const,
  reasons: (pid: string) => ["projects", pid, "exclusion-reasons"] as const,
  labels: (pid: string) => ["projects", pid, "labels"] as const,
  invite: (token: string) => ["invite", token] as const,
};

/** The reviews I am a member of. One page is plenty for a dashboard; more on request. */
export const projectsQuery = queryOptions({
  queryKey: projectKeys.list,
  queryFn: async ({ signal }) =>
    unwrap(await api.GET("/api/v1/projects", { signal, params: { query: { limit: 50 } } })),
});

export const projectQuery = (pid: string) =>
  queryOptions({
    queryKey: projectKeys.detail(pid),
    queryFn: async ({ signal }) =>
      unwrap(await api.GET("/api/v1/projects/{pid}", { signal, params: { path: { pid } } })),
  });

export const membersQuery = (pid: string) =>
  queryOptions({
    queryKey: projectKeys.members(pid),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/members", {
          signal,
          params: { path: { pid }, query: { limit: 200 } },
        }),
      ),
  });

export const invitesQuery = (pid: string) =>
  queryOptions({
    queryKey: projectKeys.invites(pid),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/invites", { signal, params: { path: { pid } } }),
      ),
  });

export const criteriaQuery = (pid: string) =>
  queryOptions({
    queryKey: projectKeys.criteria(pid),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/criteria", { signal, params: { path: { pid } } }),
      ),
  });

export const keywordGroupsQuery = (pid: string) =>
  queryOptions({
    queryKey: projectKeys.keywords(pid),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/keyword-groups", {
          signal,
          params: { path: { pid } },
        }),
      ),
  });

export const reasonsQuery = (pid: string) =>
  queryOptions({
    queryKey: projectKeys.reasons(pid),
    queryFn: async ({ signal }) =>
      unwrap(
        await api.GET("/api/v1/projects/{pid}/exclusion-reasons", {
          signal,
          params: { path: { pid } },
        }),
      ),
  });

export const labelsQuery = (pid: string) =>
  queryOptions({
    queryKey: projectKeys.labels(pid),
    queryFn: async ({ signal }) =>
      unwrap(await api.GET("/api/v1/projects/{pid}/labels", { signal, params: { path: { pid } } })),
  });

export const invitePreviewQuery = (token: string) =>
  queryOptions({
    queryKey: projectKeys.invite(token),
    queryFn: async ({ signal }) =>
      unwrap(await api.GET("/api/v1/invites/{token}", { signal, params: { path: { token } } })),
    retry: false,
  });

/** For route loaders: the cached project if there is one, otherwise fetch it. */
export function loadProject(queryClient: QueryClient, pid: string): Promise<Project> {
  return queryClient.query({ ...projectQuery(pid), staleTime: "static" });
}

// --- Changing things ---------------------------------------------------------------------

export async function createProject(body: ProjectCreate): Promise<Project> {
  return unwrap(await api.POST("/api/v1/projects", { body }));
}

export async function updateProject(pid: string, body: ProjectUpdate): Promise<Project> {
  return unwrap(await api.PATCH("/api/v1/projects/{pid}", { params: { path: { pid } }, body }));
}

export async function updateSettings(
  pid: string,
  settings: ProjectSettingsPatch,
): Promise<Project> {
  return updateProject(pid, { settings });
}

export async function deleteProject(pid: string): Promise<void> {
  unwrap(await api.DELETE("/api/v1/projects/{pid}", { params: { path: { pid } } }));
}

export async function transferProject(pid: string, userId: string): Promise<Project> {
  return unwrap(
    await api.POST("/api/v1/projects/{pid}/transfer", {
      params: { path: { pid } },
      body: { user_id: userId },
    }),
  );
}

export async function duplicateSetup(pid: string, title: string): Promise<Project> {
  return unwrap(
    await api.POST("/api/v1/projects/{pid}/duplicate-setup", {
      params: { path: { pid } },
      body: { title },
    }),
  );
}

export async function updateMember(
  pid: string,
  uid: string,
  body: components["schemas"]["MemberUpdate"],
): Promise<Member> {
  return unwrap(
    await api.PATCH("/api/v1/projects/{pid}/members/{uid}", {
      params: { path: { pid, uid } },
      body,
    }),
  );
}

export async function removeMember(pid: string, uid: string): Promise<void> {
  unwrap(
    await api.DELETE("/api/v1/projects/{pid}/members/{uid}", { params: { path: { pid, uid } } }),
  );
}

export async function leaveProject(pid: string): Promise<void> {
  unwrap(await api.DELETE("/api/v1/projects/{pid}/membership", { params: { path: { pid } } }));
}

export async function inviteMember(
  pid: string,
  email: string,
  role: AssignableRole,
): Promise<NewInvite> {
  return unwrap(
    await api.POST("/api/v1/projects/{pid}/invites", {
      params: { path: { pid } },
      body: { email, role },
    }),
  );
}

export async function revokeInvite(pid: string, iid: string): Promise<void> {
  unwrap(
    await api.DELETE("/api/v1/projects/{pid}/invites/{iid}", { params: { path: { pid, iid } } }),
  );
}

export async function acceptInvite(token: string): Promise<string> {
  const body = unwrap(
    await api.POST("/api/v1/invites/{token}/accept", { params: { path: { token } } }),
  );
  return body.project_id;
}

export async function addCriterion(
  pid: string,
  body: components["schemas"]["CriterionCreate"],
): Promise<Criterion> {
  return unwrap(
    await api.POST("/api/v1/projects/{pid}/criteria", { params: { path: { pid } }, body }),
  );
}

export async function updateCriterion(
  pid: string,
  cid: string,
  body: components["schemas"]["CriterionUpdate"],
): Promise<Criterion> {
  return unwrap(
    await api.PATCH("/api/v1/projects/{pid}/criteria/{cid}", {
      params: { path: { pid, cid } },
      body,
    }),
  );
}

export async function deleteCriterion(pid: string, cid: string): Promise<void> {
  unwrap(
    await api.DELETE("/api/v1/projects/{pid}/criteria/{cid}", { params: { path: { pid, cid } } }),
  );
}

export async function addKeywordGroup(
  pid: string,
  body: components["schemas"]["KeywordGroupCreate"],
): Promise<KeywordGroup> {
  return unwrap(
    await api.POST("/api/v1/projects/{pid}/keyword-groups", { params: { path: { pid } }, body }),
  );
}

export async function updateKeywordGroup(
  pid: string,
  gid: string,
  body: components["schemas"]["KeywordGroupUpdate"],
): Promise<KeywordGroup> {
  return unwrap(
    await api.PATCH("/api/v1/projects/{pid}/keyword-groups/{gid}", {
      params: { path: { pid, gid } },
      body,
    }),
  );
}

export async function deleteKeywordGroup(pid: string, gid: string): Promise<void> {
  unwrap(
    await api.DELETE("/api/v1/projects/{pid}/keyword-groups/{gid}", {
      params: { path: { pid, gid } },
    }),
  );
}

export async function addKeywords(
  pid: string,
  body: components["schemas"]["KeywordsCreate"],
): Promise<KeywordGroup> {
  return unwrap(
    await api.POST("/api/v1/projects/{pid}/keywords", { params: { path: { pid } }, body }),
  );
}

export async function deleteKeyword(pid: string, kid: string): Promise<void> {
  unwrap(
    await api.DELETE("/api/v1/projects/{pid}/keywords/{kid}", { params: { path: { pid, kid } } }),
  );
}

export async function addReason(
  pid: string,
  body: components["schemas"]["ReasonCreate"],
): Promise<Reason> {
  return unwrap(
    await api.POST("/api/v1/projects/{pid}/exclusion-reasons", {
      params: { path: { pid } },
      body,
    }),
  );
}

export async function updateReason(
  pid: string,
  rid: string,
  body: components["schemas"]["ReasonUpdate"],
): Promise<Reason> {
  return unwrap(
    await api.PATCH("/api/v1/projects/{pid}/exclusion-reasons/{rid}", {
      params: { path: { pid, rid } },
      body,
    }),
  );
}

export async function deleteReason(pid: string, rid: string): Promise<void> {
  unwrap(
    await api.DELETE("/api/v1/projects/{pid}/exclusion-reasons/{rid}", {
      params: { path: { pid, rid } },
    }),
  );
}

export async function addLabel(
  pid: string,
  body: components["schemas"]["LabelCreate"],
): Promise<Label> {
  return unwrap(
    await api.POST("/api/v1/projects/{pid}/labels", { params: { path: { pid } }, body }),
  );
}

export async function updateLabel(
  pid: string,
  lid: string,
  body: components["schemas"]["LabelUpdate"],
): Promise<Label> {
  return unwrap(
    await api.PATCH("/api/v1/projects/{pid}/labels/{lid}", {
      params: { path: { pid, lid } },
      body,
    }),
  );
}

export async function deleteLabel(pid: string, lid: string): Promise<void> {
  unwrap(
    await api.DELETE("/api/v1/projects/{pid}/labels/{lid}", { params: { path: { pid, lid } } }),
  );
}
