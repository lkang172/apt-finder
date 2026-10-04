import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import { IconBuilding } from "@/components/ui/icons";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: {
    default: "Apartment Finder — research with receipts",
    template: "%s · Apartment Finder",
  },
  description: "Evidence-backed Bay Area studio and 1BR apartment research. Every score links to its sources.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f6f5f2" },
    { media: "(prefers-color-scheme: dark)", color: "#0d0d10" },
  ],
};

const NAV_LINK_CLASS =
  "rounded-lg px-3 py-1.5 text-sm font-medium text-ink-muted transition hover:bg-surface-muted hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col font-sans">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[1000] focus:rounded-lg focus:bg-surface focus:px-4 focus:py-2 focus:shadow-lg"
        >
          Skip to content
        </a>
        <header className="border-b border-line bg-surface/90 backdrop-blur">
          <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6">
            <Link
              href="/"
              className="flex items-center gap-2.5 rounded-lg focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-accent"
            >
              <span className="grid size-9 place-items-center rounded-xl bg-accent text-xl text-accent-ink">
                <IconBuilding />
              </span>
              <span className="leading-tight">
                <span className="block text-[15px] font-semibold tracking-tight text-ink">Apartment Finder</span>
                <span className="block text-xs text-ink-faint">Research with receipts</span>
              </span>
            </Link>
            <nav aria-label="Primary" className="flex items-center gap-1">
              <Link href="/" className={NAV_LINK_CLASS}>
                Browse
              </Link>
              <Link href="/excluded" className={NAV_LINK_CLASS}>
                Excluded
              </Link>
            </nav>
          </div>
        </header>
        <main id="main" className="flex-1">
          {children}
        </main>
        <footer className="border-t border-line">
          <div className="mx-auto max-w-7xl px-4 py-6 text-xs text-ink-faint sm:px-6">
            Every score links to its evidence and original sources. Prices and availability change — verify directly with the
            property before applying or signing.
          </div>
        </footer>
      </body>
    </html>
  );
}
