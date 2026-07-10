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
          <>
            {/* Day-of-week header */}
            <div
              className="grid gap-2 mb-1.5 text-center"
              style={{ gridTemplateColumns: `repeat(${Math.min(chartDays.length, 7)}, 1fr)` }}
            >
              {chartDays.slice(0, Math.min(chartDays.length, 7)).map((item) => {
                const d = parseIsoCalendarDate(item.date);
                return (
                  <span
                    key={item.date}
                    className="text-[10px] font-semibold text-muted-foreground/60 uppercase tracking-wider"
                  >
                    {d.toLocaleDateString("en-US", { weekday: "short" })}
                  </span>
                );
              })}
            </div>
            {/* Day grid */}
            <div
              className="grid gap-2"
              style={{ gridTemplateColumns: `repeat(${Math.min(chartDays.length, 7)}, 1fr)` }}
            >
              {chartDays.map((item) => {
                const isToday = item.date === today;
                const hasAppts = item.value > 0;
                return (
                  <a
                    key={item.date}
                    href={`${appointmentsHref}?date=${item.date}`}
                    className={`
                      flex flex-col items-center justify-center gap-1 rounded-xl px-2 py-3
                      transition-all cursor-pointer select-none border
                      ${isToday
                        ? "bg-[#1F4D11] text-white shadow-sm border-[#1F4D11]"
                        : hasAppts
                          ? "bg-card text-card-foreground border-border/50 shadow-[0_1px_3px_rgba(15,23,42,0.07)] hover:shadow-[0_4px_16px_rgba(31,77,17,0.28)] hover:-translate-y-0.5 hover:border-brand-200"
                          : "bg-transparent text-muted-foreground/40 border-transparent hover:bg-softgray/60"
                      }
                    `}
                  >
                    <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide leading-none">
                      {parseIsoCalendarDate(item.date).toLocaleDateString("en-US", { weekday: "short" })}
                    </span>
                    <span className={`
                      text-[11px] leading-none
                      ${isToday ? "text-white/80" : hasAppts ? "text-muted-foreground" : "text-muted-foreground/50"}
                    `}>
                      {parseIsoCalendarDate(item.date).getDate()}
                    </span>
                    <span className={`
                      text-xl font-bold leading-none tabular-nums mt-0.5
                      ${isToday
                        ? "text-white"
                        : hasAppts
                          ? "text-[#081803]"
                          : "text-muted-foreground/40"
                      }
                    `}>
                      {item.value}
                    </span>
                    {isToday && (
                      <span className="mt-0.5 text-[9px] font-semibold uppercase tracking-wider bg-white/20 text-white rounded-full px-1.5 py-[1px] leading-none">
                        Today
                      </span>
                    )}
                  </a>
                );
              })}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
