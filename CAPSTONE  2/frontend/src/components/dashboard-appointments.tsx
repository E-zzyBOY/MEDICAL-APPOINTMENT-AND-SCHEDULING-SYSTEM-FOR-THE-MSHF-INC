"use client";

import { Badge } from "@/components/ui/badge";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import {
	Table,
	TableBody,
	TableCaption,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from "@/components/ui/table";
import { formatDate } from "@/components/formater";
import type { AppointmentRow } from "@/types";

const statusStyles: Record<string, string> = {
	"Pending Time Assignment":
		"border-transparent bg-amber-100 text-amber-700 hover:bg-amber-200",
	Scheduled: "border-transparent bg-[#4382DF] text-white hover:bg-[#4382DF]/90",
	Rescheduled:
		"border-transparent bg-[#4647AE] text-white hover:bg-[#4647AE]/90",
	"Pending Reschedule":
		"border-transparent bg-purple-100 text-purple-700 hover:bg-purple-200",
	Completed:
		"border-transparent bg-[#AACCD6]/40 text-[#112E81] hover:bg-[#AACCD6]/55",
	Cancelled:
		"border-transparent bg-destructive text-destructive-foreground hover:bg-destructive/90",
};

const avatarPalette = ["#4382DF", "#4647AE", "#112E81", "#6B9FE0"];

function initials(name: string) {
	const parts = name.trim().split(/\s+/);
	const first = parts[0]?.[0] ?? "";
	const last = parts.length > 1 ? parts[parts.length - 1]?.[0] ?? "" : "";
	return (first + last).toUpperCase() || "?";
}

export function DashboardAppointments({
	title,
	rows,
	href,
}: {
	title: string;
	rows: AppointmentRow[];
	href?: string;
}) {
	const hasSecondary = rows.some((r) => r.secondary);

	return (
		<Card className="animate-fade-up border-border/70">
			<CardHeader>
				<CardTitle className="text-[#112E81]">{title}</CardTitle>
				<CardDescription>
					{rows.length} {rows.length === 1 ? "appointment" : "appointments"}
				</CardDescription>
			</CardHeader>
			<CardContent className="px-0 pb-2">
				{rows.length === 0 ? (
					<p className="py-8 text-center text-muted-foreground">
						No appointments.
					</p>
				) : (
					<Table className="border-t">
						<TableCaption className="sr-only">
							{title}, with patient or doctor, date, and status.
						</TableCaption>
						<TableHeader>
							<TableRow>
								<TableHead className="pl-6">Name</TableHead>
								{hasSecondary ? <TableHead>Detail</TableHead> : null}
								<TableHead>Date</TableHead>
								<TableHead className="pr-6 text-right">Status</TableHead>
							</TableRow>
						</TableHeader>
						<TableBody>
							{rows.map((r, i) => (
								<TableRow className="h-14" key={i}>
									<TableCell className="pl-6 font-medium">
										<div className="flex items-center gap-3">
											<span
												className="flex size-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white"
												style={{
													backgroundColor:
														avatarPalette[i % avatarPalette.length],
												}}
											>
												{initials(r.primary)}
											</span>
											{r.primary}
										</div>
									</TableCell>
									{hasSecondary ? (
										<TableCell className="text-muted-foreground text-xs">
											{r.secondary}
										</TableCell>
									) : null}
									<TableCell className="text-muted-foreground text-xs tabular-nums">
										{formatDate(r.date, "day-month")}
										{r.time ? ` · ${r.time}` : ""}
									</TableCell>
									<TableCell className="pr-6 text-right">
										<Badge
											className={
												statusStyles[r.status] ??
												"border-border text-foreground"
											}
										>
											{r.status === "Pending Reschedule" && (
												<span className="relative mr-1.5 flex size-1.5">
													<span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-purple-400 opacity-75" />
													<span className="relative inline-flex size-1.5 rounded-full bg-purple-500" />
												</span>
											)}
											{r.status}
										</Badge>
									</TableCell>
								</TableRow>
							))}
						</TableBody>
					</Table>
				)}
			</CardContent>
		</Card>
	);
}
