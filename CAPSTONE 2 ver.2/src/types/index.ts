export type UserRole = "PATIENT" | "DOCTOR" | "SECRETARY" | "ADMIN";

export interface User {
  id: string;
  name: string;
  role: UserRole;
  avatar?: string;
  initials: string;
  email: string;
}

export type AppointmentStatus =
  | "Scheduled"
  | "Rescheduled"
  | "Completed"
  | "Cancelled";

export interface Appointment {
  id: string;
  patientName: string;
  patientInitials: string;
  doctorName: string;
  doctorSpecialty?: string;
  date: string;
  time: string;
  status: AppointmentStatus;
  type?: "Consultation" | "Follow-up" | "Check-up";
}

export interface StatCard {
  id: string;
  label: string;
  value: string | number;
  hint?: string;
  icon: string;
  trend?: {
    direction: "up" | "down";
    percentage: number;
  };
}

export interface TrendDataPoint {
  date: string;
  value: number;
}

export interface DashboardConfig {
  title: string;
  stats: StatCard[];
  appointments: Appointment[];
  trendData: TrendDataPoint[];
  trendLabel: string;
  trendValue: string | number;
  quickActions: QuickAction[];
}

export interface QuickAction {
  id: string;
  title: string;
  description: string;
  icon: string;
}
