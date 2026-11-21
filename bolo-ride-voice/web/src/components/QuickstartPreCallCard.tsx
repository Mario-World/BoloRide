"use client";

import { Loader2 } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import type { VoiceLanguage } from "@/services/api";

const LANGUAGE_OPTIONS = [
	{ value: "en", label: "English" },
	{ value: "hi", label: "हिन्दी" },
	{ value: "kn", label: "ಕನ್ನಡ" },
	{ value: "te", label: "తెలుగు" },
] as const satisfies ReadonlyArray<{ value: VoiceLanguage; label: string }>;

function isVoiceLanguage(value: string): value is VoiceLanguage {
	return LANGUAGE_OPTIONS.some((option) => option.value === value);
}

type QuickstartPreCallCardProps = {
	isLoading: boolean;
	error: string | null;
	language: VoiceLanguage;
	onLanguageChange: (language: VoiceLanguage) => void;
	onStartConversation: () => void;
};

export function QuickstartPreCallCard({
	isLoading,
	error,
	language,
	onLanguageChange,
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
				Choose a language for the assistant. It can estimate a fare and create
				a booking only after you confirm the ride details.
			</p>

			<div className="mt-6 w-full text-left">
				<label
					htmlFor="voice-language"
					className="mb-2 block text-sm font-medium text-white"
				>
					Conversation language
				</label>
				<select
					id="voice-language"
					value={language}
					disabled={isLoading}
					onChange={(event) => {
						const nextLanguage = event.currentTarget.value;
						if (isVoiceLanguage(nextLanguage)) {
							onLanguageChange(nextLanguage);
						}
					}}
					className="min-h-12 w-full rounded-lg border border-white/15 bg-[#161616] px-3 text-sm text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-60"
				>
					{LANGUAGE_OPTIONS.map((option) => (
						<option key={option.value} value={option.value}>
							{option.label}
						</option>
					))}
				</select>
				<p className="mt-2 text-xs leading-5 text-muted-foreground">
					Multilingual recognition supports all four languages and natural
					switching. Kannada and Telugu voice output requires server-side
					MURF_API_KEY configuration.
				</p>
			</div>

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
