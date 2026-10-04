"use client";

import { StateMessage } from "@/components/ui/StateMessage";

export default function ErrorBoundary({ retry }: { error: Error & { digest?: string }; retry: () => void }) {
  return (
    <div className="px-4 py-16">
      <StateMessage
        tone="error"
        title="Something went wrong while rendering this page"
        action={
          <button
            type="button"
            onClick={() => retry()}
            className="rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-accent-ink hover:bg-accent-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            Try again
          </button>
        }
      >
        <p>If the backend API was just restarted, trying again usually fixes this.</p>
      </StateMessage>
    </div>
  );
}
