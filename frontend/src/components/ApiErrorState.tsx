import { ApiError } from "@/lib/api";
import { backendUrl } from "@/lib/backend-url";
import { ReloadButton } from "./ReloadButton";
import { StateMessage } from "./ui/StateMessage";

export async function tryLoad<T>(load: () => Promise<T>): Promise<{ data: T; error: null } | { data: null; error: ApiError }> {
  try {
    return { data: await load(), error: null };
  } catch (error) {
    if (error instanceof ApiError) return { data: null, error };
    throw error;
  }
}

export function ApiErrorState({ error }: { error: ApiError }) {
  if (error.isUnreachable) {
    return (
      <StateMessage
        tone="error"
        title="Can't reach the apartment data API"
        action={<ReloadButton />}
      >
        <p>
          The backend isn&apos;t responding at <code className="rounded bg-surface-muted px-1.5 py-0.5 font-mono text-xs">{backendUrl()}</code>.
        </p>
        <p>Start the backend API server (see the project README), then reload this page.</p>
      </StateMessage>
    );
  }
  return (
    <StateMessage tone="error" title="The apartment data API returned an error">
      <p>{error.message}</p>
      <p>Check the backend logs, then reload this page.</p>
    </StateMessage>
  );
}
