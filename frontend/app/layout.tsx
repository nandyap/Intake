import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "M42 Intake Agent",
  description: "AI use-case intake and CAFÉ derivation",
};

const NAV = [
  { href: "/", label: "Submissions" },
  { href: "/submit", label: "New submission" },
  { href: "/artifacts", label: "Governance" },
];

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-6xl items-center gap-8 px-6 py-4">
            <Link href="/" className="flex items-baseline gap-2">
              <span className="text-lg font-semibold tracking-tight">M42</span>
              <span className="text-lg text-slate-500">Intake Agent</span>
            </Link>
            <nav className="flex gap-6 text-sm">
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="text-slate-600 transition hover:text-slate-900"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
            <span className="ml-auto rounded border border-slate-200 px-2 py-1 text-xs text-slate-500">
              Phase 1 · steps 3–22
            </span>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
