import { useMemo } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { TrendDataPoint } from "@/types";
import { ArrowUp, ArrowDown } from "lucide-react";
import { cn } from "@/lib/utils";

interface TrendChartProps {
  title?: string;
  label: string;
  value: string | number;
  data: TrendDataPoint[];
  trend?: {
    direction: "up" | "down";
    percentage: number;
  };
  delay?: number;
}

export function TrendChart({
  title = "Trend",
  label,
  value,
  data,
  trend,
  delay = 0,
}: TrendChartProps) {
  const animationDelay = `${delay}ms`;

  const chartGradientId = useMemo(() => `gradient-${Math.random()}`, []);

  return (
    <div
      className="col-span-full md:col-span-3 bg-surface border border-border rounded-lg p-5.5 animate-fadeIn"
      style={{ animationDelay }}
    >
      <div className="mb-4">
        <p className="text-xs font-medium text-text3 uppercase tracking-wider mb-1">
          {label}
        </p>
        <div className="flex items-baseline gap-2">
          <span className="text-3xl font-semibold font-mono text-text tracking-tight">
            {value}
          </span>
          {trend && (
            <div
              className={cn(
                "inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium",
                trend.direction === "up"
                  ? "bg-success bg-opacity-12 text-success"
                  : "bg-danger bg-opacity-12 text-danger"
              )}
            >
              {trend.direction === "up" ? (
                <ArrowUp className="h-3 w-3" />
              ) : (
                <ArrowDown className="h-3 w-3" />
              )}
              {trend.percentage}%
            </div>
          )}
        </div>
      </div>

      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={data}
            margin={{ top: 8, right: 24, left: -24, bottom: 0 }}
          >
            <defs>
              <linearGradient id={chartGradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#2dd4bf" stopOpacity={0.15} />
                <stop offset="95%" stopColor="#2dd4bf" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid
              strokeDasharray="3 3"
              vertical={false}
              stroke="#232b37"
              opacity={0.5}
            />
            <XAxis
              dataKey="date"
              stroke="#555f70"
              style={{ fontSize: "11px" }}
              strokeWidth={0}
            />
            <YAxis
              stroke="#555f70"
              style={{ fontSize: "11px" }}
              strokeWidth={0}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "#11161d",
                border: "1px solid #2c3645",
                borderRadius: "10px",
                fontSize: "12px",
              }}
              cursor={{ stroke: "#2dd4bf", strokeWidth: 1.5 }}
              labelStyle={{ color: "#e9edf1" }}
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke="#2dd4bf"
              strokeWidth={2.5}
              fill={`url(#${chartGradientId})`}
              dot={false}
              isAnimationActive={true}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
