export type UserRole = "PATIENT" | "DOCTOR" | "SECRETARY" | "ADMIN";

export interface User {
  id: string;
  name: string;
  role: UserRole;
  avatar?: string;
  initials: string;
  email: string;
  phone?: string;
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

export interface DashboardStat {
  label: string;
  value: string | number | null;
  hint?: string;
}

export interface TrendPoint {
  date: string;
  value: number;
}

export interface AppointmentRow {
  primary: string;
  secondary?: string;
  date: string;
  time?: string;
  status: string;
}

export interface QuickActionItem {
  title: string;
  description?: string;
  href: string;
}

export interface CategoryItem {
  name: string;
  href: string;
}

export interface DoctorCard {
  id: string;
  name: string;
  specialization: string;
  yearsExperience?: number | null;
  availability?: string | null;
  photoUrl?: string;
  href: string;
}

export interface HeroAppointment {
  doctorName: string;
  specialty?: string;
  photoUrl?: string | null;
  date: string;
  time: string;
  location?: string;
  href: string;
}

export interface CarouselSlideData {
  id: string;
  title: string;
  description: string;
  ctaLabel: string;
  href: string;
  icon: "calendar" | "doctors" | "shield";
  theme: "navy" | "teal" | "violet";
}

export interface DashboardData {
  userName?: string;
  userPhotoUrl?: string | null;
  unreadCount?: number;
  greeting?: string;
  heroAppointment?: HeroAppointment | null;
  searchHref?: string;
  carouselSlides?: CarouselSlideData[];
  stats: DashboardStat[];
  trend?: TrendPoint[];
  trendLabel?: string;
  appointmentsTitle: string;
  appointmentsHref?: string;
  appointments: AppointmentRow[];
  pastAppointmentsTitle?: string;
  pastAppointmentsHref?: string;
  pastAppointments?: AppointmentRow[];
  quickActions?: QuickActionItem[];
  categories?: CategoryItem[];
  categoriesHref?: string;
  doctors?: DoctorCard[];
  doctorsHref?: string;
}
