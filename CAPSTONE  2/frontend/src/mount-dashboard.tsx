import { createRoot } from "react-dom/client";
import { Dashboard } from "@/components/dashboard";
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

	createRoot(root).render(<Dashboard data={data} dataUrl={dataUrl} />);
}
