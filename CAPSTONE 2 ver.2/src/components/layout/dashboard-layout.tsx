import { useState } from "react";
import { User, DashboardConfig } from "@/types";
import { Sidebar } from "./sidebar";
import { Header } from "./header";
import { StatCard } from "@/components/dashboard/stat-card";
import { TrendChart } from "@/components/dashboard/trend-chart";
import { AppointmentsTable } from "@/components/dashboard/appointments-table";
import { QuickActions } from "@/components/dashboard/quick-actions";

interface NavItem {
  id: string;
  label: string;
  icon: string;
}

interface DashboardLayoutProps {
  user: User;
  config: DashboardConfig;
  navItems: NavItem[];
  activeNav: string;
  onNavChange: (itemId: string) => void;
  onSignOut?: () => void;
}

export function DashboardLayout({
  user,
  config,
  navItems,
  activeNav,
  onNavChange,
  onSignOut,
}: DashboardLayoutProps) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="flex h-screen bg-bg">
      {/* Sidebar */}
      <Sidebar
        user={user}
        navItems={navItems}
        activeItem={activeNav}
        onNavChange={onNavChange}
        onSignOut={onSignOut}
        onToggleMobile={setMobileOpen}
      />

      {/* Main Content */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Header */}
        <Header title={config.title} user={user} />

        {/* Content */}
        <main className="flex-1 overflow-y-auto lg:ml-56">
          <div className="grid auto-rows-max grid-cols-1 gap-3.5 p-6 md:grid-cols-2 lg:grid-cols-4 max-w-6xl mx-auto">
            {/* Trend Chart */}
            <TrendChart
              label={config.trendLabel}
              value={config.trendValue}
              data={config.trendData}
              delay={0}
            />

            {/* Stat Cards */}
            {config.stats.map((stat, index) => (
              <StatCard
                key={stat.id}
                {...stat}
                delay={(index + 1) * 60}
              />
            ))}

            {/* Appointments Table */}
            <AppointmentsTable
              title={`${config.appointments.length > 0 ? "Upcoming" : "No"} Appointments`}
              appointments={config.appointments}
              delay={(config.stats.length + 2) * 60}
            />

            {/* Quick Actions */}
            <QuickActions
              actions={config.quickActions}
              delay={(config.stats.length + 3) * 60}
            />
          </div>
        </main>
      </div>
    </div>
  );
}
