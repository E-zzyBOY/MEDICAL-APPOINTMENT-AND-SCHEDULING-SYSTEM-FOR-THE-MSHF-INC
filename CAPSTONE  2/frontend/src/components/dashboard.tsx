import { DashboardAppointments } from "@/components/dashboard-appointments";
import { TrendChart } from "@/components/sales-chart";
import { DashboardStats } from "@/components/stats";
import { QuickActions } from "@/components/quick-actions";
import { usePollingData } from "@/hooks/use-polling-data";
import type { DashboardData } from "@/types";

export function Dashboard({
	data,
	dataUrl,
}: {
	data: DashboardData;
	dataUrl: string;
}) {
	const live = usePollingData(data, dataUrl, 15000);
	const firstName = live.userName?.split(" ")[0];

	return (
		<div className="flex flex-1 flex-col gap-6 py-6">
			<div className="flex flex-col gap-1">
				<h1 className="font-semibold text-xl leading-tight">
					{firstName ? `Welcome back, ${firstName}!` : "Welcome back!"}
				</h1>
				<p className="text-base text-muted-foreground">
					let's get things done.
				</p>
			</div>

			<div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
				<DashboardStats stats={live.stats} />
			</div>

			{live.trend && (
				<TrendChart data={live.trend} label={live.trendLabel || ""} />
			)}

			<div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
				<DashboardAppointments
					title={live.appointmentsTitle}
					rows={live.appointments}
					href={live.appointmentsHref}
				/>
				{live.pastAppointments && (
					<DashboardAppointments
						title={live.pastAppointmentsTitle || ""}
						rows={live.pastAppointments}
						href={live.pastAppointmentsHref}
					/>
				)}
			</div>

			{live.quickActions && live.quickActions.length > 0 && (
				<QuickActions actions={live.quickActions} />
			)}
		</div>
	);
}
