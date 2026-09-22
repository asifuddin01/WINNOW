import { useMutation, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { toast } from "sonner";

import { errorMessage } from "@/api/client";

/**
 * A change to a review: refresh what it affects, say so, and put the server's own
 * sentence on screen when it refuses (guide 11.6).
 */
export function useProjectMutation<TVariables, TData>(
  mutationFn: (variables: TVariables) => Promise<TData>,
  { invalidate, success }: { invalidate: QueryKey[]; success?: string },
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: async () => {
      await Promise.all(invalidate.map((queryKey) => queryClient.invalidateQueries({ queryKey })));
      if (success) toast.success(success);
    },
    onError: (error: unknown) => {
      toast.error(errorMessage(error));
    },
  });
}
