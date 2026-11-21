import type { Metadata } from 'next'
import Link from 'next/link'

import BoloRideDemo from '@/components/BoloRideDemo'

export const metadata: Metadata = {
  title: 'Bolo Ride demo',
  description: 'Try the simulated Bolo Ride booking and payment workflow.',
}

export default function DemoPage() {
  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6 lg:px-8">
        <Link
          href="/"
          className="inline-flex min-h-11 items-center gap-2 rounded-full border border-border bg-card px-4 text-sm font-medium text-foreground transition hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <span aria-hidden="true">←</span>
          Agora voice starter
        </Link>
        <BoloRideDemo />
      </div>
    </main>
  )
}
