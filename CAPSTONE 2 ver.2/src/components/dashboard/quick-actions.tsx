import { QuickAction } from "@/types";
import * as LucideIcons from "lucide-react";
import { ChevronRight } from "lucide-react";

interface QuickActionsProps {
  actions: QuickAction[];
  delay?: number;
}

export function QuickActions({ actions, delay = 0 }: QuickActionsProps) {
  const animationDelay = `${delay}ms`;

  return (
    <div
      className="col-span-full md:col-span-2 bg-surface border border-border rounded-lg overflow-hidden animate-fadeIn"
      style={{ animationDelay }}
    >
      <div className="px-5.5 py-4 border-b border-border">
        <h3 className="text-sm font-semibold text-text">Quick Actions</h3>
        <p className="text-xs text-text3 mt-1">Shortcuts to common tasks</p>
      </div>

      <div className="divide-y divide-border">
        {actions.map((action) => {
          const IconComponent = (LucideIcons as any)[action.icon] || LucideIcons.Zap;

          return (
            <button
              key={action.id}
              className="w-full px-5.5 py-3.5 text-left transition-all hover:bg-surface2 hover:bg-opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent group"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-3 flex-1 min-w-0">
                  <div className="mt-0.5 flex h-8 w-8 items-center justify-center rounded bg-accent bg-opacity-12 flex-shrink-0 group-hover:bg-opacity-20 transition-colors">
                    <IconComponent className="h-4 w-4 text-accent" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs font-medium text-text">{action.title}</p>
                    <p className="text-xs text-text3 truncate">{action.description}</p>
                  </div>
                </div>
                <ChevronRight className="h-4 w-4 text-text3 mt-0.5 flex-shrink-0 group-hover:text-accent transition-colors" />
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
