import { useState } from "react";
import { User, UserRole } from "@/types";
import { cn } from "@/lib/utils";
import * as LucideIcons from "lucide-react";
import { Menu, X } from "lucide-react";

interface NavItem {
  id: string;
  label: string;
  icon: string;
}

interface SidebarProps {
  user: User;
  navItems: NavItem[];
  activeItem: string;
  onNavChange: (itemId: string) => void;
  onSignOut?: () => void;
  onToggleMobile?: (open: boolean) => void;
}

const roleLabels: Record<UserRole, string> = {
  PATIENT: "Patient",
  DOCTOR: "Doctor",
  SECRETARY: "Secretary",
  ADMIN: "Administrator",
};

export function Sidebar({
  user,
  navItems,
  activeItem,
  onNavChange,
  onSignOut,
  onToggleMobile,
}: SidebarProps) {
  const [mobileOpen, setMobileOpen] = useState(false);

  const toggleMobile = () => {
    setMobileOpen(!mobileOpen);
    onToggleMobile?.(!mobileOpen);
  };

  const SidebarContent = () => (
    <div className="flex h-full flex-col">
      {/* Logo */}
      <div className="flex items-center gap-2.5 border-b border-border px-5 py-5.5">
        <div className="flex h-8.5 w-8.5 items-center justify-center rounded-lg bg-gradient-to-br from-accent to-blue text-xs font-bold text-gray-900 flex-shrink-0">
          M
        </div>
        <div className="min-w-0 leading-5">
          <h1 className="text-sm font-semibold tracking-tighter">MSHFI</h1>
          <p className="text-xs text-text3">Mindalano</p>
        </div>
      </div>

      {/* Role Badge */}
      <div className="px-5 pt-3.5">
        <div className="inline-flex items-center rounded-full bg-accent-glow px-2.5 py-1 text-xs font-semibold uppercase tracking-wider text-accent border border-accent border-opacity-25">
          {roleLabels[user.role]}
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-2.5 py-2.5">
        <div className="text-xs font-semibold uppercase tracking-widest text-text3 px-2.5 py-3.5">
          Main
        </div>

        {navItems.map((item) => {
          const IconComponent = (LucideIcons as any)[item.icon] || LucideIcons.Square;
          const isActive = item.id === activeItem;

          return (
            <button
              key={item.id}
              onClick={() => {
                onNavChange(item.id);
                setMobileOpen(false);
              }}
              className={cn(
                "w-full flex items-center gap-2.5 px-2.5 py-2 rounded text-xs leading-4 transition-all mb-0.5",
                isActive
                  ? "bg-accent-glow text-accent font-medium"
                  : "text-text2 hover:bg-surface2 hover:text-text"
              )}
            >
              <IconComponent className="h-4 w-4 flex-shrink-0" />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>

      {/* User Footer */}
      <div className="border-t border-border px-4 py-3.5 flex items-center gap-2.5">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-accent to-purple text-xs font-semibold text-gray-900 flex-shrink-0">
          {user.initials}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium truncate">{user.name}</p>
          <p className="text-xs text-text3 truncate">{roleLabels[user.role]}</p>
        </div>
        <button
          onClick={onSignOut}
          className="text-text3 hover:text-danger transition-colors flex-shrink-0"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );

  return (
    <>
      {/* Mobile Toggle */}
      <button
        onClick={toggleMobile}
        className="fixed left-4 top-4 z-50 lg:hidden flex h-9 w-9 items-center justify-center rounded bg-surface border border-border2 text-text"
      >
        <Menu className="h-4 w-4" />
      </button>

      {/* Desktop Sidebar */}
      <aside className="hidden lg:fixed lg:left-0 lg:top-0 lg:flex lg:h-screen lg:w-56 lg:flex-col lg:border-r lg:border-border lg:bg-surface">
        <SidebarContent />
      </aside>

      {/* Mobile Sidebar */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden flex">
          <div
            className="absolute inset-0 bg-black bg-opacity-60 backdrop-blur-sm"
            onClick={() => setMobileOpen(false)}
          />
          <aside className="relative w-56 bg-surface border-r border-border overflow-y-auto animate-fadeIn">
            <SidebarContent />
          </aside>
        </div>
      )}
    </>
  );
}
