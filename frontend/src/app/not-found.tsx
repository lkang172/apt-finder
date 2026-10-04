import Link from "next/link";
import { StateMessage } from "@/components/ui/StateMessage";

export default function NotFound() {
  return (
    <div className="px-4 py-16">
      <StateMessage
        title="Page not found"
        action={
          <Link href="/" className="rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-accent-ink hover:bg-accent-hover">
            Browse apartments
          </Link>
        }
      >
        <p>This property may have been removed by a hard filter or no longer exists in the latest data.</p>
      </StateMessage>
    </div>
  );
}
