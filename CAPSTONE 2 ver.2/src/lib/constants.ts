import { UserRole } from "@/types";

export const roleLabels: Record<UserRole, string> = {
  PATIENT: "Patient",
  DOCTOR: "Doctor",
  SECRETARY: "Secretary",
  ADMIN: "Administrator",
};

export const PATIENT_NAV = [
  { id: "dashboard", label: "Dashboard", icon: "LayoutDashboard" },
  { id: "appointments", label: "My Appointments", icon: "Calendar" },
  { id: "book", label: "Book Appointment", icon: "Plus" },
  { id: "records", label: "Medical Records", icon: "FileText" },
  { id: "notifications", label: "Notifications", icon: "Bell" },
];

export const DOCTOR_NAV = [
  { id: "dashboard", label: "Dashboard", icon: "LayoutDashboard" },
  { id: "schedule", label: "My Schedule", icon: "Clock" },
  { id: "appointments", label: "Appointments", icon: "Calendar" },
  { id: "patients", label: "My Patients", icon: "Users" },
  { id: "notifications", label: "Notifications", icon: "Bell" },
];

export const SECRETARY_NAV = [
  { id: "dashboard", label: "Dashboard", icon: "LayoutDashboard" },
  { id: "appointments", label: "Appointments", icon: "Calendar" },
  { id: "patients", label: "Patients", icon: "Users" },
  { id: "schedules", label: "Doctor Schedules", icon: "Clock" },
  { id: "notifications", label: "Notifications", icon: "Bell" },
];

export const ADMIN_NAV = [
  { id: "dashboard", label: "Dashboard", icon: "LayoutDashboard" },
  { id: "users", label: "Manage Users", icon: "Settings" },
  { id: "overview", label: "Appointments Overview", icon: "BarChart3" },
  { id: "feedback", label: "Feedback & Logs", icon: "MessageCircle" },
  { id: "notifications", label: "Notifications", icon: "Bell" },
];
