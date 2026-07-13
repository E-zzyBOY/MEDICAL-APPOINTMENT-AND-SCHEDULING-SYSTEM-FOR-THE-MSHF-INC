import { createRoot } from "react-dom/client";
import { AdminDashboard } from "@/components/admin-dashboard";
import { Dashboard } from "@/components/dashboard";
import { PatientDashboard } from "@/components/patient-dashboard";
import type { DashboardData } from "@/types";
import "@/index.css";

export function mountDashboard(role: string) {
	const dataEl = document.getElementById("dashboard-data");
	const root = document.getElementById("react-dashboard-root");
	if (!dataEl || !root) return;

	const data = JSON.parse(dataEl.textContent || "{}") as DashboardData;
	root.setAttribute("data-role", role);

	const rolePrefix =
		role === "admin" ? "admin-panel" : role;
	const dataUrl = `/${rolePrefix}/dashboard/data/`;

	// The patient home has its own dedicated layout (ported from the mobile
	// app design); the admin gets a system-analytics overview; doctor and
	// secretary keep the shared worklist Dashboard.
	const page =
		role === "patient" ? (
			<PatientDashboard data={data} dataUrl={dataUrl} />
		) : role === "admin" ? (
			<AdminDashboard data={data} dataUrl={dataUrl} />
		) : (
			<Dashboard data={data} dataUrl={dataUrl} />
		);

	createRoot(root).render(page);
}
