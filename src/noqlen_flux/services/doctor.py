from __future__ import annotations

from noqlen_flux.results import FluxResult, Status
from noqlen_flux.services.base import FluxService


class DoctorService(FluxService):
    operation = "doctor"

    def run(self) -> FluxResult:
        result = self.result(
            Status.SUCCESS,
            network=False,
            downloads=False,
            imports=False,
            cleanup=False,
            library_writes=False,
        )
        result.steps.append(
            self.step(
                "bootstrap-status",
                Status.SUCCESS,
                "Noqlen Flux Core bootstrap is available; real workflows are not implemented.",
            )
        )
        return result.finish()
