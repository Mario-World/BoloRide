from __future__ import annotations

from dataclasses import dataclass
from math import ceil, hypot

from .schemas import FareEstimateRequest, FareEstimateResponse, VehicleCategory


@dataclass(frozen=True)
class LocationResolution:
    canonical_name: str | None
    candidates: tuple[str, ...] = ()


@dataclass(frozen=True)
class SimulatedDriver:
    driver_id: str
    name: str
    vehicle: str
    eta_minutes: int


class SimulatedRideProvider:
    """Deterministic Hyderabad fare and locality simulator for development."""

    _locations = {
        "madhapur": ("Madhapur", (0.0, 0.0)),
        "gachibowli": ("Gachibowli", (5.0, 0.0)),
        "hitech city": ("Hitech City", (1.5, 0.0)),
        "kondapur": ("Kondapur", (3.0, 0.5)),
        "jubilee hills": ("Jubilee Hills", (-3.0, 1.0)),
        "banjara hills": ("Banjara Hills", (-5.0, 1.0)),
        "charminar": ("Charminar", (-10.0, -5.0)),
        "secunderabad": ("Secunderabad", (-11.0, 7.0)),
        "rajiv gandhi international airport": (
            "Rajiv Gandhi International Airport",
            (-15.0, -10.0),
        ),
    }
    _ambiguous_locations = {
        "railway station": (
            "Secunderabad Railway Station",
            "Hyderabad Deccan (Nampally) Railway Station",
        ),
        "bus station": (
            "MGBS Bus Station",
            "JBS Bus Station",
        ),
    }
    _base_fare = {
        VehicleCategory.BIKE: 50,
        VehicleCategory.AUTO: 80,
        VehicleCategory.SEDAN: 120,
    }
    _per_km = {
        VehicleCategory.BIKE: 14,
        VehicleCategory.AUTO: 22,
        VehicleCategory.SEDAN: 30,
    }
    _capacity = {
        VehicleCategory.BIKE: 1,
        VehicleCategory.AUTO: 3,
        VehicleCategory.SEDAN: 4,
    }

    def max_passengers(self, category: VehicleCategory) -> int:
        return self._capacity[category]

    def resolve_location(self, value: str) -> LocationResolution:
        normalized = " ".join(value.casefold().split())
        if normalized in self._ambiguous_locations:
            return LocationResolution(None, self._ambiguous_locations[normalized])
        known = self._locations.get(normalized)
        if known is None:
            return LocationResolution(None)
        return LocationResolution(known[0])

    def estimate_fare(self, request: FareEstimateRequest) -> FareEstimateResponse:
        pickup = self.resolve_location(request.pickup)
        destination = self.resolve_location(request.destination)
        clarifications: dict[str, list[str]] = {}
        for field, resolution in (("pickup", pickup), ("destination", destination)):
            if resolution.canonical_name is None:
                clarifications[field] = list(resolution.candidates)

        if clarifications:
            return FareEstimateResponse(
                status="needs_clarification",
                fare=None,
                clarifications=clarifications,
            )
        if pickup.canonical_name == destination.canonical_name:
            return FareEstimateResponse(
                status="needs_clarification",
                fare=None,
                clarifications={"destination": ["Choose a destination different from pickup."]},
            )
        if request.passenger_count > self._capacity[request.vehicle_category]:
            return FareEstimateResponse(
                status="needs_clarification",
                fare=None,
                clarifications={
                    "passenger_count": [
                        f"{request.vehicle_category.value} supports up to "
                        f"{self._capacity[request.vehicle_category]} passenger(s)."
                    ]
                },
            )

        pickup_point = self._locations[" ".join(request.pickup.casefold().split())][1]
        destination_point = self._locations[
            " ".join(request.destination.casefold().split())
        ][1]
        distance_km = hypot(
            destination_point[0] - pickup_point[0],
            destination_point[1] - pickup_point[1],
        )
        rounded_distance = round(distance_km, 1)
        fare = self._base_fare[request.vehicle_category] + ceil(
            distance_km * self._per_km[request.vehicle_category]
        )
        return FareEstimateResponse(
            status="estimated",
            fare=fare,
            distance_km=rounded_distance,
        )

    def assign_driver(self, booking_id: str) -> SimulatedDriver:
        suffix = booking_id.replace("-", "")[-6:].upper()
        return SimulatedDriver(
            driver_id=f"sim-driver-{suffix}",
            name="Ravi Kumar",
            vehicle=f"Simulated sedan · TS09 {suffix[:2]} {suffix[2:4]}",
            eta_minutes=7,
        )
