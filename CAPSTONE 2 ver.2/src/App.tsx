import { useState } from "react";
import { UserRole } from "@/types";
import { DashboardLayout } from "@/components/layout/dashboard-layout";
import { USERS, PATIENT_DASHBOARD, DOCTOR_DASHBOARD, SECRETARY_DASHBOARD, ADMIN_DASHBOARD } from "@/data/mock-data";
import { PATIENT_NAV, DOCTOR_NAV, SECRETARY_NAV, ADMIN_NAV } from "@/lib/constants";

type DashboardRole = "PATIENT" | "DOCTOR" | "SECRETARY" | "ADMIN";

export function App() {
  const [currentRole, setCurrentRole] = useState<DashboardRole>("PATIENT");
  const [activeNav, setActiveNav] = useState("dashboard");

  const roleConfig = {
    PATIENT: {
      user: USERS.patient,
      config: PATIENT_DASHBOARD,
      nav: PATIENT_NAV,
    },
    DOCTOR: {
      user: USERS.doctor,
      config: DOCTOR_DASHBOARD,
      nav: DOCTOR_NAV,
    },
    SECRETARY: {
      user: USERS.secretary,
      config: SECRETARY_DASHBOARD,
      nav: SECRETARY_NAV,
    },
    ADMIN: {
      user: USERS.admin,
      config: ADMIN_DASHBOARD,
      nav: ADMIN_NAV,
    },
  };

  const current = roleConfig[currentRole];

  return (
    <>
      {/* Role Switcher Demo - Top overlay */}
      <div className="fixed top-4 right-4 z-50 flex gap-2">
        {(["PATIENT", "DOCTOR", "SECRETARY", "ADMIN"] as DashboardRole[]).map(
          (role) => (
            <button
              key={role}
              onClick={() => {
                setCurrentRole(role);
                setActiveNav("dashboard");
              }}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                currentRole === role
                  ? "bg-brand-blue text-white shadow-md"
                  : "bg-white text-slate-700 border border-slate-200 hover:bg-slate-50"
              }`}
            >
              {role}
            </button>
          )
        )}
      </div>

      {/* Dashboard */}
      <DashboardLayout
        user={current.user}
        config={current.config}
        navItems={current.nav}
        activeNav={activeNav}
        onNavChange={setActiveNav}
        onSignOut={() => console.log("Sign out clicked")}
      />
    </>
  );
}
