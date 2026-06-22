import { cn } from "@/lib/utils";
import type React from "react";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import type { DashboardStat } from "@/types";

export function DashboardStats({ stats }: { stats: DashboardStat[] }) {
	return (
		<>
			{stats.map((s) => (
				<StatCard key={s.label} stat={s} />
			))}
		</>
	);
}

function StatCard({
	stat,
	className,
	...props
}: React.ComponentProps<typeof Card> & { stat: DashboardStat }) {
	const { label, value, hint } = stat;
	const displayValue = value ?? "—";
	return (
		<Card
			className={cn("rounded-none bg-background shadow-none ring-0", className)}
			{...props}
		>
			<CardHeader className="flex flex-row items-center justify-between">
				<CardTitle className="font-normal text-muted-foreground text-xs tracking-wide">
					{label}
				</CardTitle>
				{hint && (
					<CardDescription className="text-xs tabular-nums">
						{hint}
					</CardDescription>
				)}
			</CardHeader>
			<CardContent className="flex flex-row items-center gap-2">
				<p className="font-medium text-xl tabular-nums">{displayValue}</p>
			</CardContent>
		</Card>
	);
}
