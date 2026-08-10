from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass


@dataclass(frozen=True)
class PlynomeryKalorimetryAllocation:
    title: str
    identifiers: tuple[str, ...]


@dataclass(frozen=True)
class PlynomeryMeterNode:
    identifikace: str
    children: tuple["PlynomeryMeterNode", ...] = ()
    kalorimetry_allocations: tuple[PlynomeryKalorimetryAllocation, ...] = ()

    def iter_identifiers(self) -> Iterator[str]:
        yield self.identifikace
        for child in self.children:
            yield from child.iter_identifiers()

    def iter_kalorimetry_identifiers(self) -> Iterator[str]:
        for allocation in self.kalorimetry_allocations:
            yield from allocation.identifiers
        for child in self.children:
            yield from child.iter_kalorimetry_identifiers()


@dataclass(frozen=True)
class PlynomeryBranchConfig:
    key: str
    title: str
    billing_ident: str
    submeters: tuple[PlynomeryMeterNode, ...] = ()
    residual_label: str | None = None
    kalorimetry_allocations: tuple[PlynomeryKalorimetryAllocation, ...] = ()

    @property
    def direct_submeter_idents(self) -> tuple[str, ...]:
        return tuple(node.identifikace for node in self.submeters)

    @property
    def all_submeter_idents(self) -> tuple[str, ...]:
        return _unique_identifiers(
            identifier
            for submeter in self.submeters
            for identifier in submeter.iter_identifiers()
        )

    @property
    def all_kalorimetry_idents(self) -> tuple[str, ...]:
        return _unique_identifiers(
            (
                identifier
                for allocation in self.kalorimetry_allocations
                for identifier in allocation.identifiers
            ),
            (
                identifier
                for submeter in self.submeters
                for identifier in submeter.iter_kalorimetry_identifiers()
            ),
        )


def _unique_identifiers(*identifier_groups: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for identifiers in identifier_groups:
        for identifier in identifiers:
            normalized = str(identifier).strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
    return tuple(result)


PLYNOMERY_BRANCH_CONFIGS: tuple[PlynomeryBranchConfig, ...] = (
    PlynomeryBranchConfig(
        key="INNOGY_A",
        title="INNOGY A",
        billing_ident="INNOGY_A",
        kalorimetry_allocations=(
            PlynomeryKalorimetryAllocation(
                title="Budova A - rozpočet podle kalorimetrů",
                identifiers=("Amt1", "Amt2", "Amt3"),
            ),
        ),
    ),
    PlynomeryBranchConfig(
        key="INNOGY_B",
        title="INNOGY B",
        billing_ident="INNOGY_B",
        submeters=(PlynomeryMeterNode("Bk_P1"),),
        residual_label="Budova B - zbytek po odečtení Bk_P1",
    ),
    PlynomeryBranchConfig(
        key="INNOGY_E",
        title="INNOGY E",
        billing_ident="INNOGY_E",
    ),
    PlynomeryBranchConfig(
        key="INNOGY_F",
        title="INNOGY F",
        billing_ident="INNOGY_F",
    ),
    PlynomeryBranchConfig(
        key="INNOGY_G",
        title="INNOGY G",
        billing_ident="INNOGY_G",
        submeters=(
            PlynomeryMeterNode(
                "G_P1",
                kalorimetry_allocations=(
                    PlynomeryKalorimetryAllocation(
                        title="G_P1 - rozpočet podle kalorimetrů",
                        identifiers=("Gmt1", "Gmt2", "Gmt3", "Gmt4", "Gmt5"),
                    ),
                ),
            ),
            PlynomeryMeterNode(
                "G_P3",
                kalorimetry_allocations=(
                    PlynomeryKalorimetryAllocation(
                        title="G_P3 - rozpočet podle kalorimetrů",
                        identifiers=("Gmt6", "Gmt7", "Gmt8"),
                    ),
                ),
            ),
        ),
    ),
    PlynomeryBranchConfig(
        key="INNOGY_K",
        title="INNOGY K",
        billing_ident="INNOGY_K",
        submeters=(
            PlynomeryMeterNode("K_P1"),
            PlynomeryMeterNode("K_P2"),
            PlynomeryMeterNode("K_P3"),
            PlynomeryMeterNode("K_P4"),
            PlynomeryMeterNode("K_P5"),
        ),
    ),
    PlynomeryBranchConfig(
        key="INNOGY_L",
        title="INNOGY L",
        billing_ident="INNOGY_L",
        submeters=(
            PlynomeryMeterNode("L1_P1"),
            PlynomeryMeterNode("L5_P1"),
            PlynomeryMeterNode("L6_P1"),
            PlynomeryMeterNode(
                "L2-L3_P8",
                children=(
                    PlynomeryMeterNode("L2-L3_P1"),
                    PlynomeryMeterNode("L2-L3_P2"),
                    PlynomeryMeterNode("L2-L3_P3"),
                    PlynomeryMeterNode("L2-L3_P4"),
                    PlynomeryMeterNode("L2-L3_P5"),
                    PlynomeryMeterNode("L2-L3_P7"),
                ),
            ),
        ),
    ),
)


PLYNOMERY_BRANCH_CONFIG_BY_BILLING_IDENT: dict[str, PlynomeryBranchConfig] = {
    config.billing_ident: config for config in PLYNOMERY_BRANCH_CONFIGS
}


def get_plynomery_branch_config(billing_ident: str) -> PlynomeryBranchConfig:
    normalized = str(billing_ident or "").strip()
    try:
        return PLYNOMERY_BRANCH_CONFIG_BY_BILLING_IDENT[normalized]
    except KeyError as exc:
        allowed_values = ", ".join(sorted(PLYNOMERY_BRANCH_CONFIG_BY_BILLING_IDENT))
        raise ValueError(
            f"Neznamy fakturacni plynomer '{billing_ident}'. Povolené hodnoty: {allowed_values}."
        ) from exc
