"use client";

import {
	Area,
	AreaChart,
	Bar,
	BarChart,
	CartesianGrid,
	LabelList,
	XAxis,
	YAxis,
} from "recharts";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import {
	ChartContainer,
	ChartTooltip,
	ChartTooltipContent,
} from "@/components/ui/chart";
import { DashboardStats } from "@/components/stats";
import { QuickActions } from "@/components/quick-actions";
import { usePollingData } from "@/hooks/use-polling-data";
import type { DashboardData, LabelValue } from "@/types";

/*
 * Admin overview — system-wide analytics, deliberately different from the
 * doctor/secretary dashboards (which are worklist-oriented). Single-hue
 * charts: each panel encodes one measure, so identity is carried by the
 * axis labels and titles, never by color alone.
 */

const BRAND_GREEN = "#5E9A3C"; // appointment volume + status mix
const TEAL = "#0D9488"; // doctor workload (second sequential context)
const AMBER = "#C98500"; // ratings (ordinal, own hue)

function volumeChartData(trend: { date: string; value: number }[]) {
	return trend.map((p) => {
		const d = new Date(`${p.date}T00:00:00`);
		return {
			...p,
			shortDate: d.toLocaleDateString("en-US", {
				month: "short",
				day: "numeric",
			}),
		};
	});
}

function VolumeCard({ trend, label }: { trend: { date: string; value: number }[]; label: string }) {
	const data = volumeChartData(trend);
	return (
		<Card className="animate-fade-up border-border/70">
			<CardHeader>
				<CardTitle className="text-base text-[#081803]">
					Appointment volume
				</CardTitle>
				<CardDescription>
					{label} booked per day, last 30 days (excludes pending assignment).
				</CardDescription>
			</CardHeader>
			<CardContent>
				<ChartContainer
					config={{ value: { label, color: BRAND_GREEN } }}
					className="aspect-auto h-56 w-full"
				>
					<AreaChart data={data} margin={{ left: 0, right: 8, top: 4 }}>
						<defs>
							<linearGradient id="adminVolumeFill" x1="0" y1="0" x2="0" y2="1">
								<stop offset="0%" stopColor={BRAND_GREEN} stopOpacity={0.28} />
								<stop offset="100%" stopColor={BRAND_GREEN} stopOpacity={0.03} />
							</linearGradient>
						</defs>
						<CartesianGrid vertical={false} strokeDasharray="3 3" />
						<XAxis
							dataKey="shortDate"
							tickLine={false}
							axisLine={false}
							tickMargin={8}
							minTickGap={28}
						/>
						<YAxis
							allowDecimals={false}
							width={28}
							tickLine={false}
							axisLine={false}
						/>
						<ChartTooltip
							cursor={{ stroke: "#c3c2b7", strokeWidth: 1 }}
							content={<ChartTooltipContent indicator="line" nameKey="value" labelKey="shortDate" />}
						/>
						<Area
							dataKey="value"
							type="monotone"
							stroke={BRAND_GREEN}
							strokeWidth={2}
							fill="url(#adminVolumeFill)"
							activeDot={{ r: 4 }}
						/>
					</AreaChart>
				</ChartContainer>
			</CardContent>
		</Card>
	);
}

function HorizontalBarCard({
	title,
	description,
	items,
	color,
	delay,
}: {
	title: string;
	description: string;
	items: LabelValue[];
	color: string;
	delay?: number;
}) {
	const height = Math.max(items.length * 44, 120);
	return (
		<Card
			className="animate-fade-up border-border/70"
			style={delay ? { animationDelay: `${delay}ms` } : undefined}
		>
			<CardHeader>
				<CardTitle className="text-base text-[#081803]">{title}</CardTitle>
				<CardDescription>{description}</CardDescription>
			</CardHeader>
			<CardContent>
				{items.length === 0 ? (
					<p className="py-8 text-center text-sm text-muted-foreground">
						No data yet.
					</p>
				) : (
					<ChartContainer
						config={{ value: { label: title, color } }}
						className="aspect-auto w-full"
						style={{ height }}
					>
						<BarChart
							data={items}
							layout="vertical"
							margin={{ left: 8, right: 36, top: 0, bottom: 0 }}
						>
							<XAxis type="number" hide />
							<YAxis
								dataKey="label"
								type="category"
								width={124}
								tickLine={false}
								axisLine={false}
								tick={{ fontSize: 12 }}
							/>
							<ChartTooltip
								cursor={{ fill: "rgba(0,0,0,0.04)" }}
								content={<ChartTooltipContent hideLabel nameKey="value" />}
							/>
							<Bar
								dataKey="value"
								fill={color}
								radius={[0, 4, 4, 0]}
								barSize={18}
							>
								<LabelList
									dataKey="value"
									position="right"
									className="fill-foreground"
									fontSize={12}
								/>
							</Bar>
						</BarChart>
					</ChartContainer>
				)}
			</CardContent>
		</Card>
	);
}

function RatingsCard({ items, delay }: { items: LabelValue[]; delay?: number }) {
	const total = items.reduce((sum, r) => sum + r.value, 0);
	return (
		<Card
			className="animate-fade-up border-border/70"
			style={delay ? { animationDelay: `${delay}ms` } : undefined}
		>
			<CardHeader>
				<CardTitle className="text-base text-[#081803]">
					Patient feedback ratings
				</CardTitle>
				<CardDescription>
					{total > 0
						? `Distribution of ${total} rating${total === 1 ? "" : "s"} submitted.`
						: "Distribution of submitted ratings."}
				</CardDescription>
			</CardHeader>
			<CardContent>
				{total === 0 ? (
					<p className="py-8 text-center text-sm text-muted-foreground">
						No feedback submitted yet.
					</p>
				) : (
					<ChartContainer
						config={{ value: { label: "Ratings", color: AMBER } }}
						className="aspect-auto h-48 w-full"
					>
						<BarChart data={items} margin={{ left: 0, right: 8, top: 16 }}>
							<CartesianGrid vertical={false} strokeDasharray="3 3" />
							<XAxis
								dataKey="label"
								tickLine={false}
								axisLine={false}
								tickMargin={8}
							/>
							<YAxis allowDecimals={false} width={28} tickLine={false} axisLine={false} />
							<ChartTooltip
								cursor={{ fill: "rgba(0,0,0,0.04)" }}
								content={<ChartTooltipContent hideLabel nameKey="value" />}
							/>
							<Bar dataKey="value" fill={AMBER} radius={[4, 4, 0, 0]} barSize={36}>
								<LabelList
									dataKey="value"
									position="top"
									className="fill-foreground"
									fontSize={12}
								/>
							</Bar>
						</BarChart>
					</ChartContainer>
				)}
			</CardContent>
		</Card>
	);
}

export function AdminDashboard({
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
					Here's how the whole system is doing.
				</p>
			</div>

			{/* KPI row */}
			<div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-7">
				<DashboardStats stats={live.stats} />
			</div>

			{/* 30-day volume */}
			{live.trend && live.trend.length > 0 && (
				<VolumeCard trend={live.trend} label={live.trendLabel || "Appointments"} />
			)}

			{/* Status mix + doctor workload */}
			<div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
				{live.statusBreakdown && (
					<HorizontalBarCard
						title="Appointments by status"
						description="Every appointment in the system, grouped by its current status."
						items={live.statusBreakdown}
						color={BRAND_GREEN}
						delay={120}
					/>
				)}
				{live.doctorLoad && (
					<HorizontalBarCard
						title="Doctor workload"
						description="Total appointments handled per doctor (cancelled excluded)."
						items={live.doctorLoad}
						color={TEAL}
						delay={180}
					/>
				)}
			</div>

			{/* Ratings + quick actions */}
			<div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
				{live.ratingDist && <RatingsCard items={live.ratingDist} delay={240} />}
				{live.quickActions && live.quickActions.length > 0 && (
					<QuickActions actions={live.quickActions} />
				)}
			</div>
		</div>
	);
}
