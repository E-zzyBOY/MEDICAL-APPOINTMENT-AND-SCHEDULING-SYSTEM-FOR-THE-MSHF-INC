import { useState } from "react";
import {
	Bell,
	Search,
	SlidersHorizontal,
	Heart,
	ArrowRight,
	Clock,
	MapPin,
	Stethoscope,
	HeartPulse,
	Brain,
	Baby,
	Bone,
	Eye,
	Smile,
	Syringe,
	Activity,
	User,
} from "lucide-react";
import { usePollingData } from "@/hooks/use-polling-data";
import type { DashboardData, DoctorCard, CategoryItem } from "@/types";

/* ────────────────────────────────────────────────────────────────────────
   Patient home — ported from the "DesignbyAwais" mobile mockup.
   Section order matches the design exactly:
   header → search → Browse by Specialty → Featured Doctors → Upcoming
   Appointment. Ratings were intentionally left out (no patient-visible
   ratings exist in this system); the ♡ button is a local-only toggle.
   ──────────────────────────────────────────────────────────────────────── */

declare global {
	interface Window {
		htmx?: {
			ajax: (
				verb: string,
				url: string,
				options: { target: string; swap: string }
			) => void;
		};
	}
}

function openNotificationsModal() {
	if (window.htmx) {
		window.htmx.ajax("GET", "/notifications/panel/", {
			target: "#modal-root",
			swap: "innerHTML",
		});
	} else {
		window.location.href = "/notifications/";
	}
}

/* ── Header: avatar · "Welcome back, Name 👋" · bell with badge ────────── */

function WelcomeHeader({
	greeting,
	name,
	photoUrl,
	unreadCount,
}: {
	greeting: string;
	name?: string;
	photoUrl?: string | null;
	unreadCount?: number;
}) {
	return (
		<div className="flex items-center gap-3.5">
			<div className="size-12 md:size-14 shrink-0 rounded-full overflow-hidden bg-[#DCF4F8] flex items-center justify-center ring-2 ring-white shadow-sm">
				{photoUrl ? (
					<img src={photoUrl} alt="" className="h-full w-full object-cover" />
				) : (
					<User className="size-6 text-[#2AAFC4]" />
				)}
			</div>
			<div className="min-w-0 flex-1">
				<p className="text-sm text-[#6B7280] leading-tight">{greeting},</p>
				<h1 className="font-bold text-xl md:text-2xl text-[#1F2937] leading-tight truncate">
					{name}{" "}
					<span aria-hidden="true" className="align-middle">
						👋
					</span>
				</h1>
			</div>
			{/* The site header already shows a bell on desktop, so this one is
			    mobile-only to avoid two bells stacked in view. */}
			<button
				type="button"
				onClick={openNotificationsModal}
				aria-label="Notifications"
				className="md:hidden relative flex size-11 shrink-0 items-center justify-center rounded-full bg-white border border-[#E5E7EB] text-[#1F2937] shadow-sm active:scale-95 transition-transform"
			>
				<Bell className="size-5" />
				{(unreadCount ?? 0) > 0 && (
					<span className="absolute -top-1 -right-1 min-w-[20px] h-5 px-1 flex items-center justify-center rounded-full bg-[#EF4444] text-white text-[11px] font-bold leading-none ring-2 ring-white">
						{unreadCount}
					</span>
				)}
			</button>
		</div>
	);
}

/* ── Search bar with filter button ─────────────────────────────────────── */

function SearchBar({ baseHref }: { baseHref: string }) {
	const [query, setQuery] = useState("");
	const go = () => {
		const url = query.trim()
			? `${baseHref}?q=${encodeURIComponent(query.trim())}`
			: baseHref;
		window.location.href = url;
	};

	return (
		<div className="flex items-stretch gap-2.5">
			<div className="flex flex-1 items-center gap-3 bg-white border border-[#E5E7EB] rounded-2xl px-4 py-3.5 shadow-sm">
				<Search className="size-5 text-[#9CA3AF] shrink-0" />
				<input
					type="text"
					value={query}
					onChange={(e) => setQuery(e.target.value)}
					onKeyDown={(e) => {
						if (e.key === "Enter") go();
					}}
					placeholder="Search doctors, specialties..."
					className="flex-1 min-w-0 bg-transparent border-0 p-0 text-sm text-[#1F2937] placeholder-[#9CA3AF] focus:outline-none focus:ring-0"
				/>
			</div>
			<button
				type="button"
				onClick={go}
				aria-label="Search filters"
				className="flex size-[52px] shrink-0 items-center justify-center rounded-2xl bg-white border border-[#E5E7EB] text-[#1F2937] shadow-sm hover:border-[#2AAFC4] hover:text-[#2AAFC4] transition-colors"
			>
				<SlidersHorizontal className="size-5" />
			</button>
		</div>
	);
}

/* ── Browse by Specialty chips ─────────────────────────────────────────── */

const SPECIALTY_ICONS: [RegExp, React.ComponentType<{ className?: string }>][] =
	[
		[/cardio|heart/i, HeartPulse],
		[/derma|skin/i, Smile],
		[/pedia|child|baby/i, Baby],
		[/neuro|brain/i, Brain],
		[/ortho|bone/i, Bone],
		[/ophthal|eye|optic/i, Eye],
		[/dent|tooth/i, Smile],
		[/immuno|vaccine/i, Syringe],
		[/internal|medicine|physician|general/i, Stethoscope],
	];

function specialtyIcon(name: string) {
	for (const [pattern, Icon] of SPECIALTY_ICONS) {
		if (pattern.test(name)) return Icon;
	}
	return Activity;
}

function SectionHeading({ title, href }: { title: string; href?: string }) {
	return (
		<div className="flex items-center justify-between mb-3.5">
			<h2 className="font-bold text-lg text-[#1F2937]">{title}</h2>
			{href && (
				<a
					href={href}
					className="text-sm font-medium text-[#2AAFC4] hover:underline"
				>
					View all
				</a>
			)}
		</div>
	);
}

function SpecialtyChips({
	items,
	href,
}: {
	items: CategoryItem[];
	href?: string;
}) {
	if (!items || items.length === 0) return null;
	return (
		<div className="animate-fade-up" style={{ animationDelay: "60ms" }}>
			<SectionHeading title="Browse by Specialty" href={href} />
			<div className="flex gap-3 overflow-x-auto pb-2 -mx-1 px-1 snap-x md:flex-wrap md:overflow-visible">
				{items.map((item, i) => {
					const Icon = specialtyIcon(item.name);
					const active = i === 0;
					return (
						<a
							key={item.name}
							href={item.href}
							className={
								"flex w-[104px] shrink-0 snap-start flex-col items-center justify-center gap-2.5 rounded-2xl px-2 py-4 text-center transition-all " +
								(active
									? "bg-gradient-to-b from-[#52C2D5] to-[#2AAFC4] text-white shadow-[0_8px_20px_rgba(42,175,196,0.35)]"
									: "bg-white border border-[#E5E7EB] text-[#1F2937] shadow-sm hover:border-[#2AAFC4]/60 hover:shadow-md")
							}
						>
							<span
								className={
									"flex size-11 items-center justify-center rounded-full " +
									(active ? "bg-white/20" : "bg-[#F5F7FA]")
								}
							>
								<Icon
									className={
										"size-5 " + (active ? "text-white" : "text-[#1F2937]")
									}
								/>
							</span>
							<span className="text-xs font-medium leading-snug line-clamp-2">
								{item.name}
							</span>
						</a>
					);
				})}
			</div>
		</div>
	);
}

/* ── Featured Doctors cards ────────────────────────────────────────────── */

function FeaturedDoctorCard({ doc }: { doc: DoctorCard }) {
	// Local-only ♡ — visual affordance from the design; nothing is saved.
	const [liked, setLiked] = useState(false);
	const availableToday = doc.availability === "Available Today";

	return (
		<div className="relative flex w-[240px] md:w-auto shrink-0 snap-start flex-col overflow-hidden rounded-3xl bg-white border border-[#E5E7EB] shadow-sm hover:shadow-lg transition-shadow">
			<a href={doc.href} className="block h-40 md:h-44 w-full bg-[#DCF4F8]">
				{doc.photoUrl ? (
					<img
						src={doc.photoUrl}
						alt={doc.name}
						className="h-full w-full object-cover"
					/>
				) : (
					<span className="flex h-full w-full items-center justify-center">
						<Stethoscope className="size-10 text-[#2AAFC4]" />
					</span>
				)}
			</a>
			<button
				type="button"
				onClick={() => setLiked((v) => !v)}
				aria-label={liked ? "Remove from favorites" : "Add to favorites"}
				aria-pressed={liked}
				className="absolute top-3 right-3 flex size-9 items-center justify-center rounded-full bg-white/95 shadow-md active:scale-90 transition-transform"
			>
				<Heart
					className={
						"size-4.5 " +
						(liked ? "fill-[#EF4444] text-[#EF4444]" : "text-[#6B7280]")
					}
				/>
			</button>
			<div className="flex flex-1 flex-col p-4">
				<a href={doc.href}>
					<p className="font-bold text-base text-[#1F2937] truncate">
						{doc.name}
					</p>
				</a>
				<p className="text-sm text-[#6B7280] truncate mt-0.5">
					{doc.specialization || "General Physician"}
				</p>
				{doc.yearsExperience != null && doc.yearsExperience > 0 && (
					<p className="text-sm text-[#6B7280] mt-0.5">
						{doc.yearsExperience}+ Years Experience
					</p>
				)}
				<div className="mt-3.5 flex items-center justify-between gap-2">
					{doc.availability ? (
						<span
							className={
								"inline-flex items-center rounded-full px-3 py-1.5 text-xs font-semibold " +
								(availableToday
									? "bg-[#E1F0E6] text-[#2F8F5B]"
									: "bg-[#DCEAFB] text-[#3568B5]")
							}
						>
							{doc.availability}
						</span>
					) : (
						<span className="inline-flex items-center rounded-full bg-[#F5F7FA] px-3 py-1.5 text-xs font-semibold text-[#6B7280]">
							View Schedule
						</span>
					)}
					<a
						href={doc.href}
						aria-label={`View ${doc.name}`}
						className="flex size-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-b from-[#52C2D5] to-[#2AAFC4] text-white shadow-[0_4px_12px_rgba(42,175,196,0.4)] hover:shadow-[0_6px_16px_rgba(42,175,196,0.5)] transition-shadow"
					>
						<ArrowRight className="size-4" />
					</a>
				</div>
			</div>
		</div>
	);
}

function FeaturedDoctors({
	doctors,
	href,
}: {
	doctors: DoctorCard[];
	href?: string;
}) {
	if (!doctors || doctors.length === 0) return null;
	return (
		<div className="animate-fade-up" style={{ animationDelay: "120ms" }}>
			<SectionHeading title="Featured Doctors" href={href} />
			<div className="flex gap-4 overflow-x-auto pb-2 -mx-1 px-1 snap-x md:grid md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 md:overflow-visible">
				{doctors.map((doc) => (
					<FeaturedDoctorCard key={doc.id} doc={doc} />
				))}
			</div>
		</div>
	);
}

/* ── Upcoming Appointment hero card ────────────────────────────────────── */

function UpcomingAppointmentCard({
	appt,
}: {
	appt: NonNullable<DashboardData["heroAppointment"]>;
}) {
	const d = new Date(appt.date + "T00:00:00");
	const month = d.toLocaleDateString("en-US", { month: "short" });
	const day = d.getDate();
	const weekday = d.toLocaleDateString("en-US", { weekday: "short" });

	return (
		<div className="animate-fade-up" style={{ animationDelay: "180ms" }}>
			<SectionHeading title="Upcoming Appointment" />
			<div className="rounded-3xl bg-gradient-to-r from-[#2AAFC4] to-[#17758B] p-4 md:p-5 shadow-[0_12px_30px_rgba(42,175,196,0.35)]">
				<div className="flex items-center gap-4">
					<div className="flex w-[68px] shrink-0 flex-col items-center justify-center rounded-2xl bg-white px-2 py-3 text-center shadow-sm">
						<span className="text-xs font-medium text-[#6B7280]">{month}</span>
						<span className="text-2xl font-bold leading-tight text-[#1F2937]">
							{day}
						</span>
						<span className="text-xs font-medium text-[#6B7280]">
							{weekday}
						</span>
					</div>
					<div className="hidden sm:flex size-14 shrink-0 items-center justify-center overflow-hidden rounded-2xl bg-white/20 ring-2 ring-white/40">
						{appt.photoUrl ? (
							<img
								src={appt.photoUrl}
								alt=""
								className="h-full w-full object-cover"
							/>
						) : (
							<Stethoscope className="size-6 text-white" />
						)}
					</div>
					<div className="min-w-0 flex-1 text-white">
						<p className="font-bold text-base md:text-lg truncate">
							{appt.doctorName}
						</p>
						{appt.specialty && (
							<p className="text-sm text-white/85 truncate">{appt.specialty}</p>
						)}
						<p className="mt-1.5 flex items-center gap-1.5 text-sm text-white/95">
							<Clock className="size-3.5 shrink-0" />
							{appt.time}
						</p>
						{appt.location && (
							<p className="mt-0.5 flex items-center gap-1.5 text-sm text-white/95 truncate">
								<MapPin className="size-3.5 shrink-0" />
								{appt.location}
							</p>
						)}
					</div>
					<a
						href={appt.href}
						className="shrink-0 self-center rounded-full bg-white px-4 py-2.5 text-sm font-semibold text-[#1F2937] shadow-sm hover:bg-[#F0FAFB] transition-colors"
					>
						View Details
					</a>
				</div>
			</div>
		</div>
	);
}

function NoAppointmentCard({ bookHref }: { bookHref: string }) {
	return (
		<div className="animate-fade-up" style={{ animationDelay: "180ms" }}>
			<SectionHeading title="Upcoming Appointment" />
			<div className="flex items-center justify-between gap-4 rounded-3xl bg-gradient-to-r from-[#2AAFC4] to-[#17758B] p-5 shadow-[0_12px_30px_rgba(42,175,196,0.35)]">
				<div className="text-white">
					<p className="font-bold text-base md:text-lg">
						No upcoming appointment
					</p>
					<p className="text-sm text-white/85 mt-0.5">
						Book a visit with one of our specialists.
					</p>
				</div>
				<a
					href={bookHref}
					className="shrink-0 rounded-full bg-white px-4 py-2.5 text-sm font-semibold text-[#1F2937] shadow-sm hover:bg-[#F0FAFB] transition-colors"
				>
					Book Now
				</a>
			</div>
		</div>
	);
}

/* ── Page ──────────────────────────────────────────────────────────────── */

export function PatientDashboard({
	data,
	dataUrl,
}: {
	data: DashboardData;
	dataUrl: string;
}) {
	const live = usePollingData(data, dataUrl, 15000);
	const bookHref = live.searchHref || "/patient/appointments/book/";

	return (
		<div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 py-2 md:py-4">
			<WelcomeHeader
				greeting={live.greeting || "Welcome back"}
				name={live.userName}
				photoUrl={live.userPhotoUrl}
				unreadCount={live.unreadCount}
			/>

			<SearchBar baseHref={bookHref} />

			{live.categories && (
				<SpecialtyChips items={live.categories} href={live.categoriesHref} />
			)}

			{live.doctors && (
				<FeaturedDoctors doctors={live.doctors} href={live.doctorsHref} />
			)}

			{live.heroAppointment ? (
				<UpcomingAppointmentCard appt={live.heroAppointment} />
			) : (
				<NoAppointmentCard bookHref={bookHref} />
			)}
		</div>
	);
}
