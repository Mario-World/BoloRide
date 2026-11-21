"use client";

import Image from "next/image";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";

type QuickstartConversationLayoutProps = {
	statusPanel: ReactNode;
	pipelineMetrics: ReactNode;
	transcriptPanel: ReactNode;
	visualizer: ReactNode;
	controls: ReactNode;
	onEndConversation: () => void;
};

export function QuickstartConversationLayout({
	statusPanel,
	pipelineMetrics,
	transcriptPanel,
	visualizer,
	controls,
	onEndConversation,
}: QuickstartConversationLayoutProps) {
	return (
		<div className="flex min-h-0 flex-1 flex-col text-left">
			<header className="flex shrink-0 flex-col gap-3 border-b border-border px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4 sm:px-6 sm:py-3 md:h-[76px] md:py-0">
				<div className="flex min-w-0 items-center gap-3">
					<Image
						src="/agora-logo-mark.svg"
						alt="Agora"
						width={40}
						height={40}
						className="h-10 w-10 shrink-0 object-contain"
					/>
					<div className="flex min-w-0 flex-col justify-center gap-1">
						<span className="truncate text-lg font-semibold leading-none tracking-[-0.025em] text-foreground">
							Bolo Ride
						</span>
						<span className="text-xs text-muted-foreground">Voice booking · English demo</span>
						{pipelineMetrics}
					</div>
				</div>

				<div className="flex items-center justify-between gap-3 sm:justify-end md:pr-1">
					{statusPanel}
					<Button
						variant="destructive"
						size="sm"
						className="min-h-11 rounded-md border border-destructive bg-transparent px-4 text-xs font-medium text-destructive hover:bg-destructive/10"
						onClick={onEndConversation}
						aria-label="End conversation with AI agent"
						title="End conversation"
					>
						End Conversation
					</Button>
				</div>
			</header>

			<div className="flex min-h-0 w-full flex-1 flex-col gap-3 px-3 pb-3 pt-3 sm:gap-4 sm:px-4 md:px-6 lg:flex-row lg:gap-0">
				<aside className="order-2 h-40 min-h-0 w-full shrink-0 sm:h-56 lg:order-1 lg:h-full lg:w-[26rem]">
					{transcriptPanel}
				</aside>

				<main className="order-1 flex min-h-0 flex-1 flex-col lg:order-2 lg:border-l lg:border-border/80 lg:pl-6">
					<div className="flex min-h-0 flex-1 flex-col pb-1 pt-1 sm:pb-3 sm:pt-3 md:pb-6">
						<div className="flex min-h-0 flex-1 items-center justify-center">
							{visualizer}
						</div>
						<div className="shrink-0 pt-4">{controls}</div>
					</div>
				</main>
			</div>
		</div>
	);
}
