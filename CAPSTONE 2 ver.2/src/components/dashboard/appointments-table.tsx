import { Appointment } from "@/types";
import { formatDate } from "@/lib/utils";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

interface AppointmentsTableProps {
  title: string;
  appointments: Appointment[];
  delay?: number;
}

const statusPillClasses: Record<string, string> = {
  Scheduled: "bg-success bg-opacity-12 text-success",
  Rescheduled: "bg-purple bg-opacity-12 text-purple",
  Completed: "bg-accent bg-opacity-12 text-accent",
  Cancelled: "bg-danger bg-opacity-12 text-danger",
};

const statusDotColors: Record<string, string> = {
  Scheduled: "bg-success",
  Rescheduled: "bg-purple",
  Completed: "bg-accent",
  Cancelled: "bg-danger",
};

export function AppointmentsTable({
  title,
  appointments,
  delay = 0,
}: AppointmentsTableProps) {
  const animationDelay = `${delay}ms`;

  if (appointments.length === 0) {
    return (
      <div
        className="col-span-full md:col-span-2 bg-surface border border-border rounded-lg p-5.5 animate-fadeIn"
        style={{ animationDelay }}
      >
        <h3 className="text-sm font-semibold mb-2">{title}</h3>
        <div className="py-12 text-center">
          <p className="text-text3 text-sm">No appointments scheduled</p>
        </div>
      </div>
    );
  }

  return (
    <div
      className="col-span-full md:col-span-2 bg-surface border border-border rounded-lg overflow-hidden animate-fadeIn"
      style={{ animationDelay }}
    >
      <div className="px-5.5 py-4 border-b border-border">
        <h3 className="text-sm font-semibold text-text">{title}</h3>
        <p className="text-xs text-text3 mt-1">
          {appointments.length} appointment{appointments.length !== 1 ? "s" : ""}
        </p>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border bg-surface2 bg-opacity-50">
              <th className="px-4 py-2.5 text-left font-medium text-text3 uppercase tracking-wider">
                Patient
              </th>
              <th className="px-4 py-2.5 text-left font-medium text-text3 uppercase tracking-wider">
                Date & Time
              </th>
              <th className="px-4 py-2.5 text-left font-medium text-text3 uppercase tracking-wider">
                Status
              </th>
            </tr>
          </thead>
          <tbody>
            {appointments.slice(0, 5).map((apt) => (
              <tr key={apt.id} className="border-b border-border hover:bg-surface2 hover:bg-opacity-50 transition-colors">
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2.5">
                    <div className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-accent to-purple text-xs font-semibold text-gray-900 flex-shrink-0">
                      {apt.patientInitials}
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs font-medium text-text truncate">
                        {apt.patientName}
                      </p>
                      <p className="text-xs text-text3 truncate">{apt.doctorName}</p>
                    </div>
                  </div>
                </td>
                <td className="px-4 py-3">
                  <div>
                    <p className="text-xs font-medium text-text">
                      {formatDate(apt.date)}
                    </p>
                    <p className="text-xs text-text3 font-mono">{apt.time}</p>
                  </div>
                </td>
                <td className="px-4 py-3">
                  <div
                    className={cn(
                      "inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium",
                      statusPillClasses[apt.status]
                    )}
                  >
                    <div
                      className={cn(
                        "h-1.5 w-1.5 rounded-full flex-shrink-0",
                        statusDotColors[apt.status]
                      )}
                    />
                    {apt.status}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {appointments.length > 5 && (
        <div className="border-t border-border px-5.5 py-3">
          <button className="flex items-center gap-1.5 text-xs font-medium text-accent hover:text-accent2 transition-colors">
            View All
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>
      )}
    </div>
  );
}
