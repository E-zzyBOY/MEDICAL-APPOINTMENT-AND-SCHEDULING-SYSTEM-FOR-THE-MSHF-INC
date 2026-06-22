import { User } from "@/types";

interface HeaderProps {
  title: string;
  user: User;
}

const roleLabelsMap: Record<string, string> = {
  PATIENT: "Patient",
  DOCTOR: "Doctor",
  SECRETARY: "Secretary",
  ADMIN: "Administrator",
};

export function Header({ title, user }: HeaderProps) {
  return (
    <header className="sticky top-0 z-20 border-b border-border bg-surface lg:ml-56">
      <div className="flex h-14 items-center justify-between px-8">
        <h1 className="text-2xl font-semibold tracking-tighter text-text">{title}</h1>

        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-accent to-purple text-xs font-semibold text-gray-900 flex-shrink-0">
            {user.initials}
          </div>
          <div className="text-right hidden sm:block">
            <p className="text-xs font-medium text-text">{user.name}</p>
            <p className="text-xs text-text3">{roleLabelsMap[user.role]}</p>
          </div>
        </div>
      </div>
    </header>
  );
}
