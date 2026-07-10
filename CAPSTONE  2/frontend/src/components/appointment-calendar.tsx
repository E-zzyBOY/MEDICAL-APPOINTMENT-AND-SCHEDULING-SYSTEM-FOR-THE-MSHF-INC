"use client";

import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
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
  const [weekOffset, setWeekOffset] = useState(0);

  const todayStr = useMemo(() => todayISO(), []);

  const chartDays = useMemo(() => {
    if (data.length === 0) return [];
    const todayDate = parseIsoCalendarDate(todayStr);
    const dateEnd = new Date(todayDate);
    dateEnd.setDate(dateEnd.getDate() + weekOffset * periodDays);
    const dateStart = new Date(dateEnd);
    dateStart.setDate(dateStart.getDate() - periodDays + 1);
    return data.filter((item) => {
      const d = parseIsoCalendarDate(item.date);
      return d >= dateStart && d <= dateEnd;
    });
  }, [data, periodDays, weekOffset, todayStr]);

  const canGoBack = useMemo(() => {
    if (data.length === 0) return false;
    const todayDate = parseIsoCalendarDate(todayStr);
    const dateEnd = new Date(todayDate);
    dateEnd.setDate(dateEnd.getDate() + (weekOffset - 1) * periodDays);
    const dateStart = new Date(dateEnd);
    dateStart.setDate(dateStart.getDate() - periodDays + 1);
    const minDate = parseIsoCalendarDate(data[0].date);
    return dateStart >= minDate;
  }, [data, periodDays, weekOffset, todayStr]);

  const dateRangeLabel = useMemo(() => {
    if (chartDays.length === 0) return "";
    const first = chartDays[0].date;
    const last = chartDays[chartDays.length - 1].date;
    const fmt = (iso: string) => {
      const d = parseIsoCalendarDate(iso);
      return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
    };
    return `${fmt(first)} – ${fmt(last)}`;
  }, [chartDays]);

  const today = todayISO();

  return (
    <Card className="animate-fade-up border-border/70 py-4 lg:col-span-3">
      <CardHeader>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 space-y-2">
            <CardTitle className="text-base">{label}</CardTitle>
            <CardDescription>
              {dateRangeLabel || `Daily count by day, last ${periodDays} days.`}
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setWeekOffset((w) => w - 1)}
              disabled={!canGoBack}
              aria-label="Previous period"
              className="flex size-8 items-center justify-center rounded-lg border border-border/60 bg-card text-muted-foreground hover:bg-accent hover:text-accent-foreground transition disabled:opacity-30 disabled:pointer-events-none"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={() => setWeekOffset((w) => Math.min(w + 1, 0))}
              disabled={weekOffset === 0}
              aria-label="Next period"
              className="flex size-8 items-center justify-center rounded-lg border border-border/60 bg-card text-muted-foreground hover:bg-accent hover:text-accent-foreground transition disabled:opacity-30 disabled:pointer-events-none"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
            <Select
              onValueChange={(v) => {
                const n = Number(v);
                if (n === 7 || n === 30) {
                  setPeriodDays(n);
                  setWeekOffset(0);
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
        </div>
      </CardHeader>
      <CardContent>
        {chartDays.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-8">
            No appointment data available for this period.
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
