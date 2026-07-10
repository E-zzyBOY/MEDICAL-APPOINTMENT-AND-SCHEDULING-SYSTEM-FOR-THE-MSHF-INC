"use client";

import { useMemo, useState } from "react";
import { parseIsoCalendarDate } from "@/components/formater";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { TrendPoint } from "@/types";

type PeriodDays = 7 | 30;

function todayISO(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function AppointmentCalendar({
  data,
  label,
  appointmentsHref,
}: {
  data: TrendPoint[];
  label: string;
  appointmentsHref: string;
}) {
  const [periodDays, setPeriodDays] = useState<PeriodDays>(7);

  const chartDays = useMemo(() => {
    if (data.length === 0) return [];
    const lastDate = parseIsoCalendarDate(data[data.length - 1].date);
    const startDate = new Date(lastDate);
    startDate.setDate(startDate.getDate() - periodDays + 1);
    return data.filter((item) => {
      const d = parseIsoCalendarDate(item.date);
      return d >= startDate && d <= lastDate;
    });
  }, [data, periodDays]);

  const today = todayISO();

  return (
    <Card className="animate-fade-up border-border/70 py-4 lg:col-span-3">
      <CardHeader>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 space-y-2">
            <CardTitle className="text-base">{label}</CardTitle>
            <CardDescription>
              Daily count by day, last {periodDays} days.
            </CardDescription>
          </div>
          <Select
            onValueChange={(v) => {
              const n = Number(v);
              if (n === 7 || n === 30) {
                setPeriodDays(n);
              }
            }}
            value={String(periodDays)}
          >
            <SelectTrigger
              aria-label="Calendar range"
              className="w-full min-w-36 sm:w-fit"
              size="sm"
            >
              <SelectValue placeholder="Range" />
            </SelectTrigger>
            <SelectContent align="end">
              <SelectItem value="7">Last 7 days</SelectItem>
              <SelectItem value="30">Last 30 days</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </CardHeader>
      <CardContent>
        {chartDays.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-8">
            No appointment data available.
          </p>
        ) : (
          <div
            className="grid gap-3"
            style={{ gridTemplateColumns: `repeat(${Math.min(chartDays.length, 7)}, 1fr)` }}
          >
            {(() => {
              const maxCount = Math.max(...chartDays.map((d) => d.value), 1);
              return chartDays.map((item) => {
                const isToday = item.date === today;
                const hasAppts = item.value > 0;
                const pct = Math.round((item.value / maxCount) * 100);
                const d = parseIsoCalendarDate(item.date);
                return (
                  <a
                    key={item.date}
                    href={`${appointmentsHref}?date=${item.date}`}
                    className={`
                      flex flex-col gap-1.5 p-4 rounded-xl
                      transition-all cursor-pointer select-none
                      ${isToday
                        ? "border-2 border-[#0D9488] shadow-sm hover:shadow-md"
                        : hasAppts
                          ? "bg-[#EFFAF9] border-l-[3px] border-l-[#0D9488] border border-y border-r-[#E2E8F0] hover:shadow-md hover:brightness-[0.98]"
                          : "bg-white border border-[#E2E8F0] hover:bg-[#F8FAFC]"
                      }
                    `}
                  >
                    {/* Top row: day name left, Today pill right */}
                    <div className="flex items-center justify-between min-h-[18px]">
                      <span className={`
                        text-[10px] font-semibold uppercase tracking-wider leading-none
                        ${isToday ? "text-[#0D9488]" : "text-[#94A3B8]"}
                      `}>
                        {d.toLocaleDateString("en-US", { weekday: "short" })}
                      </span>
                      {isToday && (
                        <span className="text-[9px] font-semibold uppercase tracking-wider bg-[#0D9488] text-white rounded-full px-2 py-[2px] leading-none">
                          Today
                        </span>
                      )}
                    </div>
                    {/* Date number */}
                    <span className={`
                      text-[13px] leading-none
                      ${hasAppts ? "text-[#334155]" : "text-[#94A3B8]"}
                    `}>
                      {d.getDate()}
                    </span>
                    {/* Count */}
                    <span className={`
                      text-[22px] font-bold leading-none tabular-nums
                      ${hasAppts ? "text-[#0D9488]" : "text-[#94A3B8]"}
                    `}>
                      {item.value}
                    </span>
                    {/* Load bar */}
                    <div className="w-full bg-[#E2E8F0] h-1.5 rounded-full overflow-hidden mt-0.5">
                      <div
                        className="h-full bg-[#0D9488] rounded-full transition-all"
                        style={{ width: `${hasAppts ? pct : 0}%` }}
                      />
                    </div>
                  </a>
                );
              });
            })()}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
