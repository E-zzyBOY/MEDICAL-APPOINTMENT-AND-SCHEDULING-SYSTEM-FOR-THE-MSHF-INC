import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import { AppointmentStatus } from "@/types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function getStatusColor(status: AppointmentStatus): string {
  switch (status) {
    case "Scheduled":
      return "bg-blue-100 text-blue-800 border-blue-300";
    case "Rescheduled":
      return "bg-indigo-100 text-indigo-800 border-indigo-300";
    case "Completed":
      return "bg-teal-100 text-teal-800 border-teal-300";
    case "Cancelled":
      return "bg-red-100 text-red-800 border-red-300";
    default:
      return "bg-gray-100 text-gray-800 border-gray-300";
  }
}

export function getStatusBgColor(status: AppointmentStatus): string {
  switch (status) {
    case "Scheduled":
      return "bg-brand-blue";
    case "Rescheduled":
      return "bg-brand-indigo";
    case "Completed":
      return "bg-brand-teal";
    case "Cancelled":
      return "bg-red-600";
    default:
      return "bg-gray-500";
  }
}

export function getIconColor(status: AppointmentStatus): string {
  switch (status) {
    case "Scheduled":
      return "text-blue-600";
    case "Rescheduled":
      return "text-indigo-600";
    case "Completed":
      return "text-teal-600";
    case "Cancelled":
      return "text-red-600";
    default:
      return "text-gray-600";
  }
}

export function formatDate(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

export function formatTime(timeString: string): string {
  return timeString;
}

export function abbreviateNumber(num: number): string {
  if (num >= 1000000) {
    return (num / 1000000).toFixed(1) + "M";
  }
  if (num >= 1000) {
    return (num / 1000).toFixed(1) + "K";
  }
  return num.toString();
}
