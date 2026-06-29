import { Search } from "lucide-react";
import { useState } from "react";

export function DoctorSearchBar({ baseHref }: { baseHref: string }) {
	const [query, setQuery] = useState("");

	const go = () => {
		const url = query.trim()
			? `${baseHref}?q=${encodeURIComponent(query.trim())}`
			: baseHref;
		window.location.href = url;
	};

	return (
		<div className="animate-fade-up flex items-center gap-2.5 bg-[#F5F5F7] rounded-xl px-4 py-3">
			<Search className="size-4 text-[#9a9aa5] shrink-0" />
			<input
				type="text"
				value={query}
				onChange={(e) => setQuery(e.target.value)}
				onKeyDown={(e) => {
					if (e.key === "Enter") go();
				}}
				placeholder="Search doctor..."
				className="flex-1 bg-transparent border-0 p-0 text-sm text-[#161622] placeholder-[#9a9aa5] focus:outline-none focus:ring-0"
			/>
		</div>
	);
}
