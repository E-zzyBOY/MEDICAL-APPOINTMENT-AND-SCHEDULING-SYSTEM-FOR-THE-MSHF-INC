import { useEffect, useRef, useState } from "react";

export function usePollingData<T>(
	initialData: T,
	url: string,
	intervalMs: number
): T {
	const [data, setData] = useState<T>(initialData);
	const intervalRef = useRef<NodeJS.Timeout | null>(null);

	useEffect(() => {
		const poll = async () => {
			try {
				const response = await fetch(url);
				if (!response.ok) {
					return;
				}
				const contentType = response.headers.get("content-type");
				if (contentType?.includes("application/json")) {
					const newData = (await response.json()) as T;
					setData(newData);
				}
			} catch {
				// Polling silently fails on network errors; data stays unchanged.
			}
		};

		poll();
		intervalRef.current = setInterval(poll, intervalMs);

		return () => {
			if (intervalRef.current) {
				clearInterval(intervalRef.current);
			}
		};
	}, [url, intervalMs]);

	return data;
}
