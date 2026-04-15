from enum import Enum
from math import log10, pi
from scipy.constants import c


#https://hubble.com/community/guides/how-to-calculate-lorawan-link-budget/
#https://www.gaussianwaves.com/2013/09/friss-free-space-propagation-model/
#https://grokipedia.com/page/Log-distance_path_loss_model

# ============================================================================
# Enumerations: Configuration and reference data
# ============================================================================

class PathLossExponent(float, Enum):
    """Path loss exponent (n) for common environments.

    Source: Friis free-space propagation model / log-distance path loss model.
    Free space follows inverse square law (n=2); higher n = faster attenuation.
    """
    FREE_SPACE        = 2.0
    URBAN_LOS         = 3.0   # Line-of-sight urban
    URBAN_SHADOWED    = 4.0   # Shadowed urban (mid-range)
    INDOOR_LOS        = 1.7   # In-building line-of-sight
    INDOOR_NLOS       = 5.0   # In-building non-line-of-sight (mid-range)
    INDOOR_OBSTRUCTED = 2.5   # Heavily obstructed in-building


class FadingMargin(Enum):
    """Fade margin with associated reliability and use case assumptions.

    Assumes Rayleigh fading conditions; actual performance varies by environment.

    Fade margin is the buffer between calculated received power and receiver
    sensitivity, accounting for multipath fading, weather, vegetation, timing
    variations, and model-reality deviations.
    """
    LOW = (10, 90.0)                           # Static outdoor, fixed sensors, good placement
    MODERATE = (15, 95.0)                      # Variable outdoor, vegetation/urban street level
    HIGH = (20, 99.0)                          # Mobile or variable conditions
    CRITICAL = (25, 99.7)                      # Critical / infrastructure
    ULTRA_CRITICAL = (30, 99.9)                # Mission-critical / infrastructure

    def margin_db(self) -> float:
        """Return fade margin in dB."""
        return float(self.value[0])

    def reliability_percent(self) -> float:
        """Return expected reliability as a percentage."""
        return float(self.value[1])


class LoRaSpreadingFactor(Enum):
    """LoRa Spreading Factor with receiver sensitivity and airtime tradeoffs.

    Source: Hubble LoRaWAN Link Budget Guide (SX1276 at 125 kHz bandwidth).
    
    LoRa's variable spreading factor creates a sensitivity range unmatched by
    other LPWAN technologies. Each SF step buys ~2.5 dB sensitivity improvement
    at the cost of doubling airtime (and proportionally doubling power consumption).
    """
    SF7 = (7, -123.0, 1)
    SF8 = (8, -126.0, 2)
    SF9 = (9, -129.0, 4)
    SF10 = (10, -132.0, 8)
    SF11 = (11, -134.0, 16)
    SF12 = (12, -137.0, 32)

    def spreading_factor(self) -> int:
        """Return the spreading factor value (7-12)."""
        return int(self.value[0])

    def sensitivity_dbm(self) -> float:
        """Return receiver sensitivity in dBm for SX1276 at 125 kHz."""
        return float(self.value[1])

    def relative_airtime(self) -> int:
        """Return relative airtime multiplier (SF7 = 1×)."""
        return int(self.value[2])


# ============================================================================
# Helper functions
# ============================================================================

def free_space_path_loss(d_0: float, f: float) -> float:
    """Compute free-space path loss in dB.

    FSPL = 20·log₁₀(4πd₀f / c)

    Args:
        d_0: Distance in metres.
        f:   Carrier frequency in Hz.

    Returns:
        Path loss in dB (positive value; higher means more loss).
    """
    return 20 * log10((4 * pi * d_0 * f) / c)


# ============================================================================
# Core Friis equation functions
# ============================================================================

def friis(
    p_t: float, g_t: float, g_r: float, d: float, f: float, l: float = 1.0
) -> float:
    """Compute received power using the basic Friis transmission equation.

    Models free-space propagation with inverse-square law (distance exponent n=2):

        Pr = Pt · Gt · Gr · (λ / (4π·d))²,   where λ = c / f

    Args:
        p_t: Transmit power in watts (linear, not dBm).
        g_t: Transmitter antenna gain as a linear ratio.
        g_r: Receiver antenna gain as a linear ratio.
        d:   Distance between antennas in metres.
        f:   Carrier frequency in Hz.
        l:   System loss factor (linear, default 1.0 means no loss).

    Returns:
        Received power in watts.
    """
    wavelength = c / f
    return p_t * g_t * g_r * (wavelength / (4 * pi * d)) ** 2 * l


def friis_dbm(p_t_dbm: float, g_t_dbi: float, g_r_dbi: float, d: float, f: float, l_db: float = 0.0) -> float:
    """Compute received power in dBm using basic Friis transmission equation.

    Free-space propagation model (inverse square law):

        Pr(dBm) = Pt(dBm) + Gt(dBi) + Gr(dBi) - FSPL(d, f) - L(dB)

    where FSPL = 20·log₁₀(4πd·f / c).    

    Args:
        p_t_dbm: Transmit power in dBm.
        g_t_dbi: Transmitter antenna gain in dBi.
        g_r_dbi: Receiver antenna gain in dBi.
        d: Distance in metres.
        f: Carrier frequency in Hz.
        l_db: Additional system losses in dB (default 0.0).

    Returns:
        Received power in dBm.
    """
    if d <= 0:
        raise ValueError("d must be > 0")
    if f <= 0:
        raise ValueError("f must be > 0")

    fspl_db = free_space_path_loss(d, f)
    return p_t_dbm + g_t_dbi + g_r_dbi - fspl_db - l_db


def log_distance_path_loss(
    p_t: float, g_t: float, g_r: float, d: float, f: float, n: PathLossExponent, l: float = 1.0, d0: float = 1.0
) -> float:
    """Compute received power using log-distance path loss model with exponent n.

    Generalises the basic Friis equation to non-ideal environments by using
    free-space propagation at reference distance d0, then applying path loss
    exponent n for actual distance d:

        Pr(d) = Pr(d0) · (d0 / d)^n,   where Pr(d0) is computed via basic Friis

    When n=2, reduces to basic Friis. Higher n models faster signal decay.

    Args:
        p_t: Transmit power in watts (linear, not dBm).
        g_t: Transmitter antenna gain as a linear ratio.
        g_r: Receiver antenna gain as a linear ratio.
        d:   Distance in metres.
        f:   Carrier frequency in Hz.
        n:   Path loss exponent; use PathLossExponent enum.
        l:   System loss factor (linear, default 1.0).
        d0:  Reference distance in metres (default 1.0 m).

    Returns:
        Received power in watts.
    """
    if d <= 0:
        raise ValueError("d must be > 0")
    if d0 <= 0:
        raise ValueError("d0 must be > 0")

    # Compute received power at reference distance d0 using basic Friis
    p_r_d0 = friis(p_t, g_t, g_r, d0, f, l)
    
    # Apply path loss exponent for actual distance
    d_eff = max(d, d0)  # Clamp to avoid extrapolation below d0
    return p_r_d0 * (d0 / d_eff) ** float(n)


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
    """Compute received power in dBm using log-distance path loss model with exponent n.

    Generalises basic Friis to non-ideal environments by using free-space
    propagation at reference distance d0, then applying path loss exponent n:

        Pr(d, dBm) = Pr(d0, dBm) - 10·n·log₁₀(d / d0)

    When n=2 and d0=1m, reduces to basic Friis. Higher n models faster decay.

    Args:
        p_t_dbm: Transmit power in dBm.
        g_t_dbi: Transmitter antenna gain in dBi.
        g_r_dbi: Receiver antenna gain in dBi.
        d: Distance in metres.
        f: Carrier frequency in Hz.
        n: Path loss exponent; use PathLossExponent enum.
        l_db: Additional system losses in dB (default 0.0).
        d0: Reference distance in metres (default 1.0 m).

    Returns:
        Received power in dBm.
    """
    if d <= 0:
        raise ValueError("d must be > 0")
    if d0 <= 0:
        raise ValueError("d0 must be > 0")
    if f <= 0:
        raise ValueError("f must be > 0")

    # Compute received power at reference distance d0 using basic Friis
    pr_d0_dbm = friis_dbm(p_t_dbm, g_t_dbi, g_r_dbi, d0, f, l_db)
    
    # Clamp very short distances to d0 so the model stays well-behaved
    d_eff = max(d, d0)

    # Apply path loss exponent for actual distance
    return pr_d0_dbm - 10 * float(n) * log10(d_eff / d0)


def max_distance_from_link_budget(
    link_budget_db: float,
    f: float,
    n: PathLossExponent,
    d0: float = 1.0,
) -> float:
    """Solve maximum range from link budget using the log-distance path loss model.

    The link works while total propagation loss is less than or equal to the
    available link budget. With path loss referenced to d0:

        PL(d) = FSPL(d0) + 10·n·log10(d / d0)

    Solving PL(d) = link_budget_db for d gives:

        d_max = d0 · 10^((link_budget_db - FSPL(d0)) / (10·n))

    Args:
        link_budget_db: Maximum allowed propagation loss in dB.
        f: Carrier frequency in Hz.
        n: Path loss exponent; use PathLossExponent enum.
        d0: Reference distance in metres (default 1.0 m).

    Returns:
        Maximum distance in metres.
    """
    if d0 <= 0:
        raise ValueError("d0 must be > 0")
    if f <= 0:
        raise ValueError("f must be > 0")

    fspl_d0_db = free_space_path_loss(d0, f)
    return d0 * 10 ** ((link_budget_db - fspl_d0_db) / (10 * float(n))) #TODO double check

# ============================================================================
# Main / Example usage
# ============================================================================

if __name__ == "__main__":

    # solve for max distance the recevier can receive

    f_hz = 868_000_000

    p_t_dbm = 14.0          # Power tx LoRaWAN
    g_t_dbi = 0.0           # Antenna gain LoRaWAN
    g_r_dbi = 0.0           # Antenna gain Node

    dirt_loss_by_label_db = {
        "dry": 0.087,
        "slightly wet": 32,
        "wet": 60,
    }

    sf = LoRaSpreadingFactor
    fm = FadingMargin
    ple = PathLossExponent
    environment = ple.INDOOR_OBSTRUCTED
    spreading_factor = sf.SF7
    fade_margin = fm.LOW

    link_budget = {
        label: p_t_dbm + g_t_dbi + g_r_dbi - loss_dirt - spreading_factor.sensitivity_dbm() - fade_margin.margin_db()
        for label, loss_dirt in dirt_loss_by_label_db.items()
    }

    max_distance = {
        label: max_distance_from_link_budget(budget, f_hz, environment)
        for label, budget in link_budget.items()
    }

    print("Link budget and max distance")
    print(f"Frequency: {f_hz / 1e6:.1f} MHz")
    print(f"Environment: {environment.name} (n={float(environment):.1f})")
    print(f"Spreading factor: SF{spreading_factor.spreading_factor()}")
    print(f"Fade margin: {fade_margin.margin_db():.1f} dB")
    print()

    for label, loss_dirt in dirt_loss_by_label_db.items():
        print(
            f"{label:12s} | dirt loss = {loss_dirt:5.1f} dB | "
            f"link budget = {link_budget[label]:6.2f} dB | max distance = {max_distance[label]:9.2f} m"
        )