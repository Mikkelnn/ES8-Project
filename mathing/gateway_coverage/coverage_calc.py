from enum import Enum
from math import log10, pi

import numpy as np


c = 299_792_458


# ============================================================================
# Enumerations
# ============================================================================

class PathLossExponent(float, Enum):
    """Path loss exponent (n) for common environments."""
    FREE_SPACE = 2.0
    URBAN_LOS = 3.0
    URBAN_SHADOWED = 4.0
    INDOOR_LOS = 1.7
    INDOOR_NLOS = 5.0
    INDOOR_OBSTRUCTED = 2.5


class LoRaSpreadingFactor(Enum):
    """LoRa spreading factor settings with approximate sensitivity values."""
    SF7 = (7, -123.0, 1)
    SF8 = (8, -126.0, 2)
    SF9 = (9, -129.0, 4)
    SF10 = (10, -132.0, 8)
    SF11 = (11, -134.0, 16)
    SF12 = (12, -137.0, 32)

    def spreading_factor(self) -> int:
        return int(self.value[0])

    def sensitivity_dbm(self) -> float:
        return float(self.value[1])

    def relative_airtime(self) -> int:
        return int(self.value[2])


# ============================================================================
# Helper functions
# ============================================================================

def free_space_path_loss(d_0: float, f: float) -> float:
    """Compute free-space path loss in dB."""
    if d_0 <= 0:
        raise ValueError("d_0 must be > 0")
    if f <= 0:
        raise ValueError("f must be > 0")
    return 20 * log10((4 * pi * d_0 * f) / c)


def empirical_cdf(samples: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return sorted samples and empirical CDF values in [0, 1]."""
    sorted_samples = np.sort(samples)
    cdf = np.arange(1, len(sorted_samples) + 1) / len(sorted_samples)
    return sorted_samples, cdf


def margin_from_channel_db(channel_gain_db: np.ndarray, reliability: float) -> float:
    """Required positive margin (dB) for a target success reliability."""
    if not (0 < reliability < 1):
        raise ValueError("reliability must be between 0 and 1")

    channel_loss_db = -channel_gain_db
    return float(max(0.0, np.quantile(channel_loss_db, reliability)))


def fading_db() -> float:
    """Rayleigh fading sample in dB."""
    r = np.random.rayleigh(scale=1 / np.sqrt(2))
    return float(20 * np.log10(r))


def shadowing_db(std_db: float = 6.0) -> float:
    """Shadowing sample in dB, modeled as Gaussian in dB."""
    return float(np.random.normal(loc=0.0, scale=std_db))


# ============================================================================
# Core Friis / log-distance functions
# ============================================================================

def friis(
    p_t: float,
    g_t: float,
    g_r: float,
    d: float,
    f: float,
    l: float = 1.0,
) -> float:
    """Compute received power using the basic Friis transmission equation."""
    if d <= 0:
        raise ValueError("d must be > 0")
    if f <= 0:
        raise ValueError("f must be > 0")
    if l <= 0:
        raise ValueError("l must be > 0")

    wavelength = c / f
    return p_t * g_t * g_r * (wavelength / (4 * pi * d)) ** 2 / l


def friis_dbm(
    p_t_dbm: float,
    g_t_dbi: float,
    g_r_dbi: float,
    d: float,
    f: float,
    l_db: float = 0.0,
) -> float:
    """Compute received power in dBm using Friis."""
    if d <= 0:
        raise ValueError("d must be > 0")
    if f <= 0:
        raise ValueError("f must be > 0")

    fspl_db = free_space_path_loss(d, f)
    return p_t_dbm + g_t_dbi + g_r_dbi - fspl_db - l_db


def log_distance_path_loss_dbm(
    p_t_dbm: float,
    g_t_dbi: float,
    g_r_dbi: float,
    d: float,
    f: float,
    n: PathLossExponent,
    l_db: float = 0.0,
    d0: float = 1.0,
) -> float:
    """Received power in dBm using log-distance path loss model."""
    if d <= 0:
        raise ValueError("d must be > 0")
    if d0 <= 0:
        raise ValueError("d0 must be > 0")
    if f <= 0:
        raise ValueError("f must be > 0")

    pr_d0_dbm = friis_dbm(p_t_dbm, g_t_dbi, g_r_dbi, d0, f, l_db)
    d_eff = max(d, d0)
    return pr_d0_dbm - 10 * float(n) * log10(d_eff / d0)


def max_distance_from_link_budget(
    link_budget_db: float,
    f: float,
    n: PathLossExponent,
    d0: float = 1.0,
) -> float:
    """Solve max range from link budget using the log-distance model."""
    if d0 <= 0:
        raise ValueError("d0 must be > 0")
    if f <= 0:
        raise ValueError("f must be > 0")

    fspl_d0_db = free_space_path_loss(d0, f)
    return d0 * 10 ** ((link_budget_db - fspl_d0_db) / (10 * float(n)))


# ============================================================================
# Simulation / calculation runner
# ============================================================================

def run_coverage_simulation() -> dict:
    """Run the full coverage simulation and return all calculated data."""
    np.random.seed(42)

    # ------------------------------------------------------------------------
    # Scenario
    # ------------------------------------------------------------------------
    f_hz = 868_000_000
    p_t_dbm = 14.0
    g_t_dbi = 0.0
    g_r_dbi = 0.0
    misc_losses_db = 0.0
    shadowing_std_db = 6.0
    d0_m = 1.0

    dirt_loss_db = {
        "dry": 0.087,
        "slightly wet": 32.0,
        "wet": 60.0,
    }

    spreading_factor = LoRaSpreadingFactor.SF7
    environments = [
        PathLossExponent.FREE_SPACE,
        PathLossExponent.URBAN_LOS,
        PathLossExponent.URBAN_SHADOWED,
    ]

    rounds = 10_000
    reliability_target = 0.99

    # ------------------------------------------------------------------------
    # Stochastic channel parts
    # ------------------------------------------------------------------------
    fading_samples = np.array([fading_db() for _ in range(rounds)])
    shadowing_samples = np.array([shadowing_db(shadowing_std_db) for _ in range(rounds)])
    composite_channel_gain_db = fading_samples + shadowing_samples

    fading_margin_db = margin_from_channel_db(fading_samples, reliability_target)
    shadowing_margin_db = margin_from_channel_db(shadowing_samples, reliability_target)
    composite_margin_db = margin_from_channel_db(composite_channel_gain_db, reliability_target)

    fading_quantile = float(np.quantile(fading_samples, 1.0 - reliability_target))
    shadowing_quantile = float(np.quantile(shadowing_samples, 1.0 - reliability_target))
    composite_quantile = float(np.quantile(composite_channel_gain_db, 1.0 - reliability_target))

    # ------------------------------------------------------------------------
    # Constant part of budget
    # ------------------------------------------------------------------------
    sensitivity_dbm = spreading_factor.sensitivity_dbm()
    base_constant_budget_db = (
        p_t_dbm
        + g_t_dbi
        + g_r_dbi
        - misc_losses_db
        - sensitivity_dbm
    )

    # ------------------------------------------------------------------------
    # Surface-dependent round-series
    # ------------------------------------------------------------------------
    surface_series = {}
    for surface_name, surface_loss_db in dirt_loss_db.items():
        constant_received_level_db = base_constant_budget_db - surface_loss_db

        constant_plus_fading_series_db = constant_received_level_db + fading_samples
        constant_plus_shadowing_series_db = constant_received_level_db + shadowing_samples
        total_received_series_db = constant_received_level_db + composite_channel_gain_db

        surface_series[surface_name] = {
            "surface_loss_db": surface_loss_db,
            "constant_received_level_db": constant_received_level_db,
            "constant_plus_fading_series_db": constant_plus_fading_series_db,
            "constant_plus_shadowing_series_db": constant_plus_shadowing_series_db,
            "total_received_series_db": total_received_series_db,
        }

    # ------------------------------------------------------------------------
    # Budgets and distances per surface condition
    # ------------------------------------------------------------------------
    budget_breakdown_rows = []
    results_rows = []

    link_budget_db = {}
    for surface, surface_loss_db in dirt_loss_db.items():
        budget = (
            base_constant_budget_db
            - surface_loss_db
            - composite_margin_db
        )
        link_budget_db[surface] = budget

        budget_breakdown_rows.append(
            [
                surface,
                f"{base_constant_budget_db:.2f}",
                f"{surface_loss_db:.2f}",
                f"{composite_margin_db:.2f}",
                f"{budget:.2f}",
            ]
        )

    for environment in environments:
        for surface, budget in link_budget_db.items():
            max_distance_m = max_distance_from_link_budget(
                link_budget_db=budget,
                f=f_hz,
                n=environment,
                d0=d0_m,
            )
            results_rows.append(
                [
                    surface,
                    environment.name,
                    f"{float(environment):.1f}",
                    f"{budget:.2f}",
                    f"{max_distance_m:.2f}",
                ]
            )

    # ------------------------------------------------------------------------
    # Info table
    # ------------------------------------------------------------------------
    info_rows = [
        ["Frequency (MHz)", f"{f_hz / 1e6:.1f}"],
        ["Reference distance d0 (m)", f"{d0_m:.1f}"],
        ["TX Power (dBm)", f"{p_t_dbm:.1f}"],
        ["TX Antenna Gain (dBi)", f"{g_t_dbi:.1f}"],
        ["RX Antenna Gain (dBi)", f"{g_r_dbi:.1f}"],
        ["Misc Losses (dB)", f"{misc_losses_db:.1f}"],
        ["Spreading Factor", f"SF{spreading_factor.spreading_factor()}"],
        ["Receiver Sensitivity (dBm)", f"{sensitivity_dbm:.1f}"],
        ["Base Constant Budget Part (dB)", f"{base_constant_budget_db:.2f}"],
        ["Simulation Rounds", f"{rounds:,}"],
        ["Reliability Target", f"{reliability_target * 100:.1f}%"],
        ["Fading Margin (dB)", f"{fading_margin_db:.2f}"],
        ["Shadowing Margin (dB)", f"{shadowing_margin_db:.2f}"],
        ["Composite Margin (dB)", f"{composite_margin_db:.2f}"],
        ["Fading Quantile (dB)", f"{fading_quantile:.2f}"],
        ["Shadowing Quantile (dB)", f"{shadowing_quantile:.2f}"],
        ["Composite Quantile (dB)", f"{composite_quantile:.2f}"],
    ]

    return {
        "config": {
            "f_hz": f_hz,
            "p_t_dbm": p_t_dbm,
            "g_t_dbi": g_t_dbi,
            "g_r_dbi": g_r_dbi,
            "misc_losses_db": misc_losses_db,
            "shadowing_std_db": shadowing_std_db,
            "d0_m": d0_m,
            "dirt_loss_db": dirt_loss_db,
            "spreading_factor": spreading_factor,
            "environments": environments,
            "rounds": rounds,
            "reliability_target": reliability_target,
            "sensitivity_dbm": sensitivity_dbm,
            "base_constant_budget_db": base_constant_budget_db,
        },
        "samples": {
            "fading_samples": fading_samples,
            "shadowing_samples": shadowing_samples,
            "composite_channel_gain_db": composite_channel_gain_db,
        },
        "statistics": {
            "fading_margin_db": fading_margin_db,
            "shadowing_margin_db": shadowing_margin_db,
            "composite_margin_db": composite_margin_db,
            "fading_quantile": fading_quantile,
            "shadowing_quantile": shadowing_quantile,
            "composite_quantile": composite_quantile,
        },
        "surface_series": surface_series,
        "tables": {
            "info_rows": info_rows,
            "budget_breakdown_rows": budget_breakdown_rows,
            "results_rows": results_rows,
        },
        "link_budget_db": link_budget_db,
    }