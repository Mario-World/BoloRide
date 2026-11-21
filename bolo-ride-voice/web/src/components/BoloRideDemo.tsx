'use client'

import { useState } from 'react'
import type { ReactNode } from 'react'

type VehicleCategory = 'bike' | 'auto' | 'sedan'
type PaymentPreference = 'cash' | 'upi' | 'card'
type PaymentOutcome = 'success' | 'failure' | 'cancelled' | 'expired'

type FareEstimate = {
  status: 'estimated' | 'needs_clarification'
  fare: number | null
  currency: 'INR'
  distance_km: number | null
  provider: 'simulated'
  clarifications: Record<string, string[]>
}

type Booking = {
  booking_id: string
  booking_reference: string
  status: 'CONFIRMED' | 'DRIVER_ASSIGNED' | 'COMPLETED' | 'CANCELLED' | 'FAILED'
  passenger_name: string | null
  pickup_location: string
  destination: string
  vehicle_category: VehicleCategory
  passenger_count: number
  payment_preference: PaymentPreference | null
  estimated_fare: number
  currency: 'INR'
  payment_confirmed: boolean
  driver: { name: string; vehicle: string; eta_minutes: number } | null
}

type Payment = {
  payment_id: string
  booking_id: string
  booking_reference: string
  status: 'CREATED' | 'PENDING' | 'VERIFIED' | 'FAILED' | 'CANCELLED' | 'EXPIRED'
  amount_minor: number
  currency: 'INR'
}

type BookingDetails = {
  passenger_name: string
  pickup_location: string
  destination: string
  vehicle_category: VehicleCategory
  passenger_count: number
  payment_preference: PaymentPreference
}

const initialDetails: BookingDetails = {
  passenger_name: '',
  pickup_location: '',
  destination: '',
  vehicle_category: 'bike',
  passenger_count: 1,
  payment_preference: 'upi',
}

async function businessRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/business/${path}`, {
    ...init,
    cache: 'no-store',
    headers: {
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...init?.headers,
    },
  })

  const payload: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const detail =
      typeof payload === 'object' && payload !== null && 'detail' in payload
        ? (payload as { detail?: unknown }).detail
        : null
    const message =
      typeof detail === 'string'
        ? detail
        : typeof detail === 'object' && detail !== null && 'message' in detail && typeof detail.message === 'string'
          ? detail.message
          : `The business service returned HTTP ${response.status}.`
    throw new Error(message)
  }

  if (payload === null) {
    throw new Error('The business service returned an empty response.')
  }
  return payload as T
}

function StatusBadge({ status }: { status: string }) {
  const isSuccess = ['VERIFIED', 'DRIVER_ASSIGNED', 'COMPLETED'].includes(status)
  const isFailed = ['FAILED', 'CANCELLED', 'EXPIRED'].includes(status)
  const style = isSuccess
    ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
    : isFailed
      ? 'border-destructive/30 bg-destructive/10 text-destructive'
      : 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300'

  return (
    <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold ${style}`}>
      {status.replace(/_/g, ' ')}
    </span>
  )
}

function Field({
  label,
  id,
  children,
}: {
  label: string
  id: string
  children: ReactNode
}) {
  return (
    <div className="grid gap-2 text-sm font-medium text-foreground">
      <label htmlFor={id}>{label}</label>
      {children}
    </div>
  )
}

const inputClass =
  'min-h-12 w-full rounded-xl border border-input bg-background px-3 text-base text-foreground outline-none transition placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60'

export default function BoloRideDemo() {
  const [details, setDetails] = useState(initialDetails)
  const [estimate, setEstimate] = useState<FareEstimate | null>(null)
  const [booking, setBooking] = useState<Booking | null>(null)
  const [payment, setPayment] = useState<Payment | null>(null)
  const [bookingKey, setBookingKey] = useState<string | null>(null)
  const [paymentKey, setPaymentKey] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function updateDetails(patch: Partial<BookingDetails>) {
    setDetails((current) => ({ ...current, ...patch }))
    setEstimate(null)
    setBookingKey(null)
  }

  async function perform(action: () => Promise<void>) {
    setBusy(true)
    setError(null)
    try {
      await action()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The request failed.')
    } finally {
      setBusy(false)
    }
  }

  function estimateFare() {
    void perform(async () => {
      const validation = await businessRequest<{
        valid: boolean
        missing_fields: string[]
        clarifications: Record<string, string[]>
        errors: string[]
      }>('bookings/validate', {
        method: 'POST',
        body: JSON.stringify({
          ...details,
          passenger_name: details.passenger_name || null,
        }),
      })
      if (!validation.valid) {
        const reasons = [
          ...validation.errors,
          ...validation.missing_fields.map((field) => `Missing ${field.replace(/_/g, ' ')}.`),
          ...Object.entries(validation.clarifications).flatMap(([field, options]) => [
            `${field.replace(/_/g, ' ')} needs clarification${options.length ? `: ${options.join(', ')}` : '.'}`,
          ]),
        ]
        throw new Error(reasons.join(' '))
      }

      const nextEstimate = await businessRequest<FareEstimate>('fare-estimates', {
        method: 'POST',
        body: JSON.stringify({
          pickup: details.pickup_location,
          destination: details.destination,
          vehicle_category: details.vehicle_category,
          passenger_count: details.passenger_count,
        }),
      })
      if (nextEstimate.status !== 'estimated' || nextEstimate.fare === null) {
        const clarifications = Object.entries(nextEstimate.clarifications)
          .map(([field, choices]) => `${field}: ${choices.join(', ') || 'choose a more specific location'}`)
          .join('; ')
        throw new Error(clarifications || 'Please clarify the trip details.')
      }
      setEstimate(nextEstimate)
      setBooking(null)
      setPayment(null)
      setPaymentKey(null)
    })
  }

  function confirmBooking() {
    if (!estimate?.fare) return
    void perform(async () => {
      const idempotencyKey = bookingKey ?? crypto.randomUUID()
      setBookingKey(idempotencyKey)
      const created = await businessRequest<Booking>('bookings', {
        method: 'POST',
        body: JSON.stringify({
          booking_details: {
            ...details,
            passenger_name: details.passenger_name || null,
            estimated_fare: estimate.fare,
            booking_confirmation: true,
          },
          idempotency_key: idempotencyKey,
        }),
      })
      setBooking(created)
    })
  }

  function createPayment() {
    if (!booking) return
    void perform(async () => {
      const idempotencyKey = paymentKey ?? crypto.randomUUID()
      setPaymentKey(idempotencyKey)
      const created = await businessRequest<Payment>('payment-orders', {
        method: 'POST',
        body: JSON.stringify({
          booking_id: booking.booking_id,
          idempotency_key: idempotencyKey,
        }),
      })
      setPayment(created)
    })
  }

  function simulatePayment(outcome: PaymentOutcome) {
    if (!payment) return
    void perform(async () => {
      const updated = await businessRequest<Payment>(`payments/${payment.payment_id}/simulate-result`, {
        method: 'POST',
        body: JSON.stringify({ outcome }),
      })
      setPayment(updated)
    })
  }

  function verifyPayment() {
    if (!payment) return
    void perform(async () => {
      const verified = await businessRequest<Payment>(`payments/${payment.payment_id}/verify`, {
        method: 'POST',
        body: JSON.stringify({}),
      })
      setPayment(verified)
      const refreshedBooking = await businessRequest<Booking>(`bookings/${booking?.booking_id}`)
      setBooking(refreshedBooking)
    })
  }

  function updateBooking(path: string, body?: object) {
    if (!booking) return
    void perform(async () => {
      const updated = await businessRequest<Booking>(path, {
        method: 'POST',
        body: JSON.stringify(body ?? {}),
      })
      setBooking(updated)
    })
  }

  function resetDemo() {
    setDetails(initialDetails)
    setEstimate(null)
    setBooking(null)
    setPayment(null)
    setBookingKey(null)
    setPaymentKey(null)
    setError(null)
  }

  const canEstimate = details.pickup_location.trim().length >= 2 && details.destination.trim().length >= 2

  return (
    <div className="mx-auto max-w-5xl pb-12 pt-8 sm:pt-12">
      <header className="mb-8 flex flex-col gap-5 sm:mb-10 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="mb-3 text-sm font-semibold uppercase tracking-[0.18em] text-primary">
            Bolo Ride · interactive demo
          </p>
          <h1 className="text-4xl font-semibold tracking-tight text-foreground sm:text-5xl">
            Your ride, one conversation away.
          </h1>
          <p className="mt-3 max-w-2xl text-base leading-7 text-muted-foreground">
            Try the real booking and mock-payment API with a simulated Hyderabad ride. No real ride or payment is
            created.
          </p>
        </div>
        <div className="rounded-2xl border border-border bg-card px-4 py-3 text-sm text-muted-foreground">
          <span className="mr-2 inline-block h-2 w-2 rounded-full bg-emerald-500" />
          Demo mode · simulated provider
        </div>
      </header>

      <div className="mb-6 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {['Estimate', 'Confirm', 'Payment', 'Ride status'].map((step, index) => {
          const complete =
            index === 0
              ? estimate !== null
              : index === 1
                ? booking !== null
                : index === 2
                  ? payment !== null
                  : booking?.status === 'COMPLETED'
          return (
            <div
              key={step}
              className={`rounded-xl border px-3 py-3 text-sm ${complete ? 'border-primary/40 bg-primary/10 text-foreground' : 'border-border bg-card text-muted-foreground'}`}
            >
              <span className="mr-2 text-xs font-semibold text-primary">0{index + 1}</span>
              {step}
            </div>
          )
        })}
      </div>

      {error && (
        <div
          role="alert"
          className="mb-6 flex items-start justify-between gap-4 rounded-2xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive"
        >
          <p>{error}</p>
          <button
            type="button"
            onClick={() => setError(null)}
            className="shrink-0 rounded px-2 py-1 font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-label="Dismiss error"
          >
            Dismiss
          </button>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <section className="rounded-3xl border border-border bg-card p-5 shadow-sm sm:p-7">
          <div className="mb-6">
            <p className="text-sm font-medium text-primary">Plan your ride</p>
            <h2 className="mt-1 text-2xl font-semibold text-card-foreground">Where to?</h2>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field id="passenger-name" label="Your name (optional)">
              <input
                id="passenger-name"
                className={inputClass}
                autoComplete="name"
                placeholder="e.g. Ananya"
                value={details.passenger_name}
                onChange={(event) => updateDetails({ passenger_name: event.target.value })}
              />
            </Field>
            <Field id="pickup-location" label="Pickup location">
              <input
                id="pickup-location"
                className={inputClass}
                autoComplete="street-address"
                placeholder="e.g. Madhapur"
                value={details.pickup_location}
                onChange={(event) => updateDetails({ pickup_location: event.target.value })}
                required
              />
            </Field>
            <Field id="destination" label="Destination">
              <input
                id="destination"
                className={inputClass}
                placeholder="e.g. Gachibowli"
                value={details.destination}
                onChange={(event) => updateDetails({ destination: event.target.value })}
                required
              />
            </Field>
            <Field id="vehicle-category" label="Vehicle">
              <select
                id="vehicle-category"
                className={inputClass}
                value={details.vehicle_category}
                onChange={(event) => updateDetails({ vehicle_category: event.target.value as VehicleCategory })}
              >
                <option value="bike">Bike · up to 1 passenger</option>
                <option value="auto">Auto · up to 3 passengers</option>
                <option value="sedan">Sedan · up to 4 passengers</option>
              </select>
            </Field>
            <Field id="passenger-count" label="Passengers">
              <select
                id="passenger-count"
                className={inputClass}
                value={details.passenger_count}
                onChange={(event) => updateDetails({ passenger_count: Number(event.target.value) })}
              >
                {[1, 2, 3, 4].map((count) => (
                  <option key={count} value={count}>
                    {count}
                  </option>
                ))}
              </select>
            </Field>
            <Field id="payment-preference" label="Payment preference">
              <select
                id="payment-preference"
                className={inputClass}
                value={details.payment_preference}
                onChange={(event) => updateDetails({ payment_preference: event.target.value as PaymentPreference })}
              >
                <option value="upi">UPI (mock)</option>
                <option value="cash">Cash</option>
                <option value="card">Card (mock)</option>
              </select>
            </Field>
          </div>

          <div className="mt-6 flex flex-col gap-3 sm:flex-row">
            <button
              type="button"
              onClick={estimateFare}
              disabled={busy || !canEstimate || booking !== null}
              className="inline-flex min-h-12 flex-1 items-center justify-center rounded-xl bg-primary px-5 font-semibold text-primary-foreground transition hover:brightness-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busy ? 'Working…' : 'Estimate fare'}
            </button>
            {booking && (
              <button
                type="button"
                onClick={resetDemo}
                className="min-h-12 rounded-xl border border-border px-5 font-semibold text-foreground transition hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                Start a new demo
              </button>
            )}
          </div>

          {estimate?.fare !== null && estimate && (
            <div className="mt-6 rounded-2xl border border-primary/30 bg-primary/5 p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Estimated fare</p>
                  <p className="mt-1 text-3xl font-semibold text-foreground">₹{estimate.fare}</p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {estimate.distance_km ?? '—'} km · simulated fare
                  </p>
                </div>
                <StatusBadge status="ESTIMATED" />
              </div>
              {!booking ? (
                <div className="mt-5">
                  <p className="mb-3 text-sm text-foreground">
                    Confirm this ride to create a booking. Nothing is booked until you choose confirm.
                  </p>
                  <button
                    type="button"
                    onClick={confirmBooking}
                    disabled={busy}
                    className="min-h-12 w-full rounded-xl bg-foreground px-5 font-semibold text-background transition hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                  >
                    {busy ? 'Creating booking…' : 'Confirm and book'}
                  </button>
                </div>
              ) : null}
            </div>
          )}
        </section>

        <aside className="space-y-6">
          <section className="rounded-3xl border border-border bg-card p-5 shadow-sm sm:p-7">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-sm font-medium text-primary">Booking</p>
                <h2 className="mt-1 text-xl font-semibold text-card-foreground">Ride details</h2>
              </div>
              {booking && <StatusBadge status={booking.status} />}
            </div>
            {booking ? (
              <div className="mt-5 space-y-4">
                <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-4">
                  <span className="text-sm text-muted-foreground">From</span>
                  <span className="font-medium text-foreground">{booking.pickup_location}</span>
                  <span className="text-sm text-muted-foreground">To</span>
                  <span className="font-medium text-foreground">{booking.destination}</span>
                  <span className="text-sm text-muted-foreground">Ride</span>
                  <span className="font-medium capitalize text-foreground">
                    {booking.vehicle_category} · {booking.passenger_count} passenger
                    {booking.passenger_count === 1 ? '' : 's'}
                  </span>
                  <span className="text-sm text-muted-foreground">Reference</span>
                  <span className="font-mono font-semibold text-foreground">{booking.booking_reference}</span>
                  <span className="text-sm text-muted-foreground">Fare</span>
                  <span className="font-semibold text-foreground">₹{booking.estimated_fare}</span>
                </div>
                {booking.driver && (
                  <div className="rounded-xl bg-muted p-4 text-sm">
                    <p className="font-semibold text-foreground">Driver assigned</p>
                    <p className="mt-1 text-muted-foreground">
                      {booking.driver.name} · {booking.driver.vehicle} · ETA {booking.driver.eta_minutes} min
                    </p>
                  </div>
                )}
                <div className="flex flex-wrap gap-2 border-t border-border pt-4">
                  {booking.status === 'CONFIRMED' && (
                    <>
                      <button
                        type="button"
                        onClick={() =>
                          updateBooking(`bookings/${booking.booking_id}/simulate/driver`, { outcome: 'assigned' })
                        }
                        disabled={busy}
                        className="min-h-11 rounded-xl border border-border px-4 text-sm font-semibold text-foreground hover:bg-muted disabled:opacity-50"
                      >
                        Assign demo driver
                      </button>
                      <button
                        type="button"
                        onClick={() => updateBooking(`bookings/${booking.booking_id}/cancel`)}
                        disabled={busy || booking.payment_confirmed}
                        className="min-h-11 rounded-xl px-4 text-sm font-semibold text-destructive hover:bg-destructive/10 disabled:opacity-50"
                      >
                        Cancel ride
                      </button>
                    </>
                  )}
                  {booking.status === 'DRIVER_ASSIGNED' && (
                    <button
                      type="button"
                      onClick={() => updateBooking(`bookings/${booking.booking_id}/simulate/complete`)}
                      disabled={busy}
                      className="min-h-11 rounded-xl border border-border px-4 text-sm font-semibold text-foreground hover:bg-muted disabled:opacity-50"
                    >
                      Complete demo ride
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() =>
                      void perform(async () => {
                        const refreshed = await businessRequest<Booking>(`bookings/${booking.booking_id}`)
                        setBooking(refreshed)
                      })
                    }
                    disabled={busy}
                    className="min-h-11 rounded-xl px-4 text-sm font-semibold text-primary hover:bg-primary/10 disabled:opacity-50"
                  >
                    Refresh status
                  </button>
                </div>
              </div>
            ) : (
              <p className="mt-5 rounded-2xl bg-muted p-4 text-sm leading-6 text-muted-foreground">
                Your confirmed booking, reference, driver and ride status will appear here.
              </p>
            )}
          </section>

          <section className="rounded-3xl border border-border bg-card p-5 shadow-sm sm:p-7">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-sm font-medium text-primary">Mock payment</p>
                <h2 className="mt-1 text-xl font-semibold text-card-foreground">Payment verification</h2>
              </div>
              {payment && <StatusBadge status={payment.status} />}
            </div>
            {!booking ? (
              <p className="mt-5 rounded-2xl bg-muted p-4 text-sm leading-6 text-muted-foreground">
                Confirm a booking before creating a mock payment order.
              </p>
            ) : !payment ? (
              <div className="mt-5">
                <p className="text-sm leading-6 text-muted-foreground">
                  The backend controls the amount. No PIN, OTP or banking credentials are requested.
                </p>
                <button
                  type="button"
                  onClick={createPayment}
                  disabled={busy || booking.status === 'CANCELLED' || booking.status === 'FAILED'}
                  className="mt-4 min-h-12 w-full rounded-xl border border-primary px-5 font-semibold text-primary transition hover:bg-primary/10 disabled:opacity-50"
                >
                  Create mock payment order
                </button>
              </div>
            ) : (
              <div className="mt-5 space-y-4">
                <div className="flex justify-between gap-4 text-sm">
                  <span className="text-muted-foreground">Amount</span>
                  <span className="font-semibold text-foreground">
                    ₹{(payment.amount_minor / 100).toFixed(2)} {payment.currency}
                  </span>
                </div>
                {payment.status === 'CREATED' && (
                  <div>
                    <p className="mb-3 text-sm text-muted-foreground">
                      Choose a simulated gateway result. A successful result remains pending until backend verification.
                    </p>
                    <div className="grid grid-cols-2 gap-2">
                      {(['success', 'failure', 'cancelled', 'expired'] as PaymentOutcome[]).map((outcome) => (
                        <button
                          key={outcome}
                          type="button"
                          onClick={() => simulatePayment(outcome)}
                          disabled={busy}
                          className="min-h-11 rounded-xl border border-border px-3 text-sm font-semibold capitalize text-foreground hover:bg-muted disabled:opacity-50"
                        >
                          {outcome}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                {payment.status === 'PENDING' && (
                  <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4">
                    <p className="text-sm font-semibold text-amber-800 dark:text-amber-200">
                      Payment pending backend verification
                    </p>
                    <p className="mt-1 text-sm text-muted-foreground">The ride is not marked paid yet.</p>
                    <button
                      type="button"
                      onClick={verifyPayment}
                      disabled={busy}
                      className="mt-3 min-h-11 w-full rounded-xl bg-foreground px-4 font-semibold text-background hover:opacity-90 disabled:opacity-50"
                    >
                      Verify with backend
                    </button>
                  </div>
                )}
                {payment.status === 'VERIFIED' && booking.payment_confirmed && (
                  <output
                    aria-live="polite"
                    className="block rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm"
                  >
                    <p className="font-semibold text-emerald-800 dark:text-emerald-200">
                      Payment verified by the backend
                    </p>
                    <p className="mt-1 text-muted-foreground">
                      Booking {booking.booking_reference} is payment-confirmed.
                    </p>
                  </output>
                )}
                {['FAILED', 'CANCELLED', 'EXPIRED'].includes(payment.status) && (
                  <output aria-live="polite" className="block rounded-xl bg-muted p-4 text-sm text-muted-foreground">
                    Payment result: {payment.status.toLowerCase()}. No payment success is shown.
                  </output>
                )}
              </div>
            )}
          </section>
        </aside>
      </div>

      <p className="mt-8 text-center text-xs leading-5 text-muted-foreground">
        Demo only. Fare, locations, driver assignment and payment outcomes are simulated. The Agora voice starter
        remains available from the link above.
      </p>
    </div>
  )
}
