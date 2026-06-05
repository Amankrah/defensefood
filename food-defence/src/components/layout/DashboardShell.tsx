"use client";

import { useState } from "react";
import Sidebar from "@/components/layout/Sidebar";
import DashboardHeader from "@/components/layout/DashboardHeader";
import { GlossaryProvider } from "@/components/shared/Glossary";

export default function DashboardShell({
  children,
}: {
  children: React.ReactNode;
}) {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <GlossaryProvider>
      <div className="min-h-screen bg-[var(--background)]">
        <div
          className="pointer-events-none fixed inset-0 bg-[radial-gradient(ellipse_70%_45%_at_50%_-15%,var(--brand-glow),transparent)]"
          aria-hidden
        />

        {sidebarOpen && (
          <button
            type="button"
            aria-label="Close navigation"
            className="fixed inset-0 z-40 bg-slate-900/50 backdrop-blur-sm lg:hidden"
            onClick={() => setSidebarOpen(false)}
          />
        )}

        <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />

        <div className="relative min-h-screen lg:ml-60">
          <DashboardHeader onMenuClick={() => setSidebarOpen(true)} />
          <main className="df-page space-y-6 p-4 sm:p-6 lg:p-8">{children}</main>
        </div>
      </div>
    </GlossaryProvider>
  );
}
