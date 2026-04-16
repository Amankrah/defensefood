import Sidebar from "@/components/layout/Sidebar";
import DashboardHeader from "@/components/layout/DashboardHeader";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-slate-100/90">
      <div
        className="pointer-events-none fixed inset-0 bg-[radial-gradient(ellipse_80%_50%_at_50%_-20%,rgba(37,99,235,0.12),transparent)]"
        aria-hidden
      />
      <Sidebar />
      <div className="relative ml-56 min-h-screen">
        <DashboardHeader />
        <main className="p-6 lg:p-8">{children}</main>
      </div>
    </div>
  );
}
