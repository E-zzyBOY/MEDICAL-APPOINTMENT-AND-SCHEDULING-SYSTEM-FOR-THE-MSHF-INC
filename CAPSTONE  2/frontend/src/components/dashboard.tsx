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

	return (
		<div className="flex flex-1 flex-col gap-6 py-6">
			<div className="flex flex-col gap-1">
				<h1 className="font-semibold text-xl leading-tight">
					Welcome back, Shaban!
				</h1>
				<p className="text-base text-muted-foreground">
					let's get things done.
				</p>
			</div>
			<div className="rounded-lg overflow-hidden border">
				<div className="grid grid-cols-1 gap-px bg-border lg:grid-cols-3">
					<DashboardStats stats={live.stats} />
					{live.trend && (
						<TrendChart
							data={live.trend}
							label={live.trendLabel || ""}
						/>
					)}
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
			</div>
			{live.quickActions && live.quickActions.length > 0 && (
				<QuickActions actions={live.quickActions} />
			)}
		</div>
	);
}
