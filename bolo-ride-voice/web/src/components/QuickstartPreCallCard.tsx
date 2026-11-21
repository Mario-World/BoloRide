"use client";

import { Loader2 } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";

type QuickstartPreCallCardProps = {
	isLoading: boolean;
	error: string | null;
	onStartConversation: () => void;
};

export function QuickstartPreCallCard({
	isLoading,
	error,
	onStartConversation,
}: QuickstartPreCallCardProps) {
	return (
		<div
			className="mx-auto flex w-[min(92vw,26.25rem)] animate-fade-up flex-col items-center rounded-[20px] border border-[#2b2b2b] px-6 py-8 text-center shadow-[0_10px_24px_rgba(0,0,0,0.28)] sm:px-10 sm:py-10"
			style={{
				backgroundImage:
					"linear-gradient(164.988deg, rgba(54,54,54,0.2) 1.0596%, rgba(0,0,0,0) 96.089%), linear-gradient(90deg, rgb(16,16,16) 0%, rgb(16,16,16) 100%)",
			}}
		>
			<p className="mb-3 rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-primary">
				Bolo Ride · Voice demo
			</p>
			<h1 className="text-[28px] font-medium leading-[1.2] text-white">
				Book a ride by talking
			</h1>
			<p className="mt-[14px] text-sm font-medium leading-6 text-muted-foreground">
				Speak with the English voice assistant. It can estimate a fare and
				create a booking only after you confirm the ride details.
			</p>

			<Button
				onClick={onStartConversation}
				disabled={isLoading}
				className="mt-8 min-h-12 w-full rounded-lg border border-primary bg-primary text-sm font-semibold text-black hover:border-white hover:bg-white hover:text-black disabled:hover:border-primary disabled:hover:bg-primary disabled:hover:text-black sm:mt-10"
				aria-label={
					isLoading
						? "Starting Bolo Ride voice booking"
						: "Start Bolo Ride voice booking"
				}
			>
				{isLoading ? (
					<>
						<Loader2 className="h-4 w-4 animate-spin" />
						Starting...
					</>
				) : (
					"Start voice booking"
				)}
			</Button>
			{error ? <p className="mt-3 text-xs text-destructive">{error}</p> : null}
			<p className="mt-4 text-xs leading-5 text-muted-foreground">
				No PINs or OTPs. Booking tools require the server-side business API to
				be configured.
			</p>
			<Link
				href="/demo"
				className="mt-4 inline-flex min-h-11 items-center justify-center rounded-lg border border-white/15 px-4 text-sm font-medium text-white transition hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
			>
				Open tap-through booking demo
			</Link>
		</div>
	);
}
