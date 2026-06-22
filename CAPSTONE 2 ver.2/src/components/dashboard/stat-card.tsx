import { StatCard as StatCardType } from "@/types";
import * as LucideIcons from "lucide-react";
import { ArrowUp, ArrowDown } from "lucide-react";
import { cn } from "@/lib/utils";

interface StatCardProps extends StatCardType {
  delay?: number;
}

const iconColorMap: Record<string, { bg: string; color: string }> = {
  Calendar: { bg: "bg-accent bg-opacity-12", color: "text-accent" },
  CheckCircle: { bg: "bg-success bg-opacity-12", color: "text-success" },
  Users: { bg: "bg-blue bg-opacity-12", color: "text-blue" },
  FileText: { bg: "bg-warning bg-opacity-12", color: "text-warning" },
  Clock: { bg: "bg-purple bg-opacity-12", color: "text-purple" },
  AlertCircle: { bg: "bg-danger bg-opacity-12", color: "text-danger" },
  RefreshCw: { bg: "bg-warning bg-opacity-12", color: "text-warning" },
  Stethoscope: { bg: "bg-accent bg-opacity-12", color: "text-accent" },
  Star: { bg: "bg-warning bg-opacity-12", color: "text-warning" },
  BarChart3: { bg: "bg-blue bg-opacity-12", color: "text-blue" },
};

export function StatCard({
  label,
  value,
  hint,
  icon,
  trend,
  delay = 0,
}: StatCardProps) {
  const IconComponent = (LucideIcons as any)[icon] || LucideIcons.Square;
  const colorMap = iconColorMap[icon] || { bg: "bg-accent bg-opacity-12", color: "text-accent" };
  const animationDelay = `${delay}ms`;

  return (
    <div
      className="col-span-1 bg-surface border border-border rounded-lg p-4.5 animate-fadeIn"
      style={{ animationDelay }}
    >
      <div className="flex items-start justify-between mb-2">
        <p className="text-xs font-medium text-text3 uppercase tracking-wider">
          {label}
        </p>
        <div className={cn("flex h-7 w-7 items-center justify-center rounded-lg flex-shrink-0", colorMap.bg)}>
          <IconComponent className={cn("h-3.5 w-3.5", colorMap.color)} />
        </div>
      </div>

      <div className="flex items-baseline gap-2">
        <span className="text-2xl font-semibold font-mono text-text tracking-tight">
          {value}
        </span>
        {trend && (
          <div
            className={cn(
              "inline-flex items-center gap-0.5 text-xs font-medium",
              trend.direction === "up" ? "text-success" : "text-danger"
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

      {hint && (
        <>
          <div className="h-px bg-border my-2.5" />
          <p className="text-xs text-text3">{hint}</p>
        </>
      )}
    </div>
  );
}
