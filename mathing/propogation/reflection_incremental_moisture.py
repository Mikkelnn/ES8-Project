import numpy as np
from scipy import constants as conts
import matplotlib.pyplot as plt

eta_0 = 120 * np.pi
f = 800e6
P_t = 10e-3
omega = 2 * np.pi * f


# -----------------------
# Core Functions
# -----------------------

def refCoef(eta_incident, eta_transmitted):
    """
    Reflection coefficient at a boundary.
    K = (eta_transmitted - eta_incident) / (eta_transmitted + eta_incident)
    Fix 2: now takes explicit incident and transmitted impedances instead of
    relying on ambiguous list indexing.
    """
    return (eta_transmitted - eta_incident) / (eta_transmitted + eta_incident)


def lossAngle(sigma, epsilon_r):
    """
    Loss tangent: tan(delta) = sigma / (omega * epsilon_0 * epsilon_r)
    """
    return sigma / (omega * conts.epsilon_0 * epsilon_r)


def complexImpedance(epsilon_r, loss_angle):
    """
    Normalised complex intrinsic impedance (relative to eta_0).
    eta = eta_0 / sqrt(epsilon_r * (1 - j*tan_delta))
    Returns the normalised factor; caller multiplies by eta_0.
    """
    return 1 / (np.sqrt(epsilon_r * (1 - 1j * loss_angle)))


def gammaCalc(epsilon_r, loss_angle):
    """
    Complex propagation constant:
    gamma = j*(omega/c) * sqrt(epsilon_r * (1 - j*tan_delta))
    Real part = attenuation (alpha), imaginary part = phase (beta).
    """
    return 1j * (omega / conts.c) * np.sqrt(epsilon_r * (1 - 1j * loss_angle))


def refCoefLen(KL, gamma, length):
    """
    Reflection coefficient loaded by round-trip through a slab of thickness L:
    K_minus = K * exp(-2*gamma*L)
    """
    return KL * np.exp(-2 * gamma * length)


def inputImpedance(eta, K_minus):
    """
    Input impedance of a loaded layer (transmission line analogy):
    eta_in = eta * (1 + K_minus) / (1 - K_minus)
    Fix 3: was previously inverted (1-K)/(1+K).
    """
    return eta * (1 + K_minus) / (1 - K_minus)


def EplusNext(KL, KminusL, Eplus):
    """
    Forward E-field transmitted across a boundary into the next layer.
    Etot at boundary = Eplus * (1 + KL)   [total field = incident + reflected]
    E+ in next layer = Etot / (1 + KminusL)
    Fix 4: removed erroneous extra attenuation exp(-gamma*L) that was
    double-counting Layer 1 decay already applied in firstMediumLoss().
    """
    Etot = Eplus * (1 + KL)
    return Etot / (1 + KminusL)


def mediumLoss(gamma, length, E):
    """
    Attenuate E-field over a distance L through a medium with propagation
    constant gamma:  E(L) = E(0) * exp(-gamma * L)
    """
    return E * np.exp(-gamma * length)


# -----------------------
# Single Set Solver
# -----------------------

def solve(epsilon_r, conductivities, lengths, label=""):
    """
    Solve E-field propagation for a single parameter set.
    Returns a dict of results.
    """
    loss_angles = [lossAngle(conductivities[i], epsilon_r[i]) for i in range(len(epsilon_r))]
    ff          = [complexImpedance(epsilon_r[i], loss_angles[i]) for i in range(len(epsilon_r))]
    gammas      = [gammaCalc(epsilon_r[i], loss_angles[i]) for i in range(len(epsilon_r))]
    eta         = [eta_0 * ff[0], eta_0 * ff[1], eta_0]

    E_0         = np.sqrt(2 * P_t * np.real(eta[0]))

    KL_last     = refCoef(eta[1], eta[2])
    KminusL     = refCoefLen(KL_last, gammas[1], lengths[1])
    eta2in      = inputImpedance(eta[1], KminusL)
    KL_first    = refCoef(eta[0], eta2in)

    EPlus1              = mediumLoss(gammas[0], lengths[0], E_0)
    EPlus2              = EplusNext(KL_first, KminusL, EPlus1)
    EPlus2_attenuated   = mediumLoss(gammas[1], lengths[1], EPlus2)
    EPlus3              = EPlus2_attenuated * (1 + KL_last)

    E_air   = np.abs(EPlus3)
    P_out   = 0.5 * (E_air ** 2) * np.real(1 / np.conj(eta_0))
    P_in    = 0.5 * (np.abs(E_0) ** 2) * np.real(1 / np.conj(eta[0]))

    return {
        "label"             : label,
        "epsilon_r"         : epsilon_r,
        "conductivities"    : conductivities,
        "lengths"           : lengths,
        "loss_angles_deg"   : [np.degrees(np.arctan(la)) for la in loss_angles],
        "eta"               : eta,
        "gammas"            : gammas,
        "E_0"               : E_0,
        "EPlus1"            : EPlus1,
        "EPlus2"            : EPlus2,
        "EPlus2_attenuated" : EPlus2_attenuated,
        "EPlus3"            : EPlus3,
        "E_air"             : E_air,
        "P_in"              : P_in,
        "P_out"             : P_out,
        "power_ratio"       : P_out / P_in,
        "loss_dB"           : 10 * np.log10(P_out / P_in),
        "KL_first"          : KL_first,
        "KL_last"           : KL_last,
    }


def print_result(r):
    print(f"""
  ═══════════════════════════════════════════
   {r['label']}
  ═══════════════════════════════════════════
   Inputs:
     epsilon_r      : {r['epsilon_r']}
     conductivities : {r['conductivities']} S/m
     lengths        : {r['lengths']} m

   Layer Properties:
     loss angle L1  : {r['loss_angles_deg'][0]:.4f} deg
     loss angle L2  : {r['loss_angles_deg'][1]:.4f} deg
     eta Layer 1    : {r['eta'][0]:.4e} Ω
     eta Layer 2    : {r['eta'][1]:.4e} Ω
     eta Air        : {r['eta'][2]:.4f} Ω
     gamma L1       : {r['gammas'][0]:.4e}  (α={r['gammas'][0].real:.4f} Np/m)
     gamma L2       : {r['gammas'][1]:.4e}  (α={r['gammas'][1].real:.4f} Np/m)

   E-field Propagation:
     E_0  (source)          : {r['E_0']:.4e} V/m
     E+   after Layer 1     : {np.abs(r['EPlus1']):.4e} V/m
     E+   entering Layer 2  : {np.abs(r['EPlus2']):.4e} V/m
     E+   after Layer 2     : {np.abs(r['EPlus2_attenuated']):.4e} V/m
     E+   in air            : {np.abs(r['EPlus3']):.4e} V/m
     |E|  in air            : {r['E_air']:.4e} V/m

   Power:
     P_in                   : {r['P_in']:.4e} W/m²
     P_out                  : {r['P_out']:.4e} W/m²
     Power ratio            : {r['power_ratio']:.6f}
     Loss                   : {r['loss_dB']:.2f} dB
""")


# -----------------------
# Multi-set Runner
# -----------------------

def run_validation_sets(all_epsilon_r, all_conductivities, all_lengths, labels=None):
    """
    Run solver for multiple parameter sets and print a comparison summary.

    Parameters
    ----------
    all_epsilon_r      : list of [eps_L1, eps_L2] lists
    all_conductivities : list of [sigma_L1, sigma_L2] lists
    all_lengths        : list of [L1, L2] lists
    labels             : optional list of strings naming each set
    """
    n = len(all_epsilon_r)
    if labels is None:
        labels = [f"Set {i+1}" for i in range(n)]

    results = []
    for i in range(n):
        r = solve(all_epsilon_r[i], all_conductivities[i], all_lengths[i], label=labels[i])
        results.append(r)
        print_result(r)

    # --- Comparison Table ---
    print("\n  ══════════════════════════════════════════════════════════════════")
    print(f"  {'Label':<20} {'P_in (W/m²)':<18} {'P_out (W/m²)':<18} {'Power Ratio':<18} {'Loss (dB)':<12} {'|E| air (V/m)'}")
    print("  ──────────────────────────────────────────────────────────────────")
    for r in results:
        print(f"  {r['label']:<20} {r['P_in']:<18.4e} {r['P_out']:<18.4e} {r['power_ratio']:<18.6f} {r['loss_dB']:<12.2f} {r['E_air']:.4e}")
    print("  ══════════════════════════════════════════════════════════════════\n")

    return results


# -----------------------
# Validation Sets
# -----------------------

if __name__ == "__main__":

    # Each entry is one validation scenario: [Layer1 value, Layer2 value]

    all_epsilon_r = [
        [1.0, 1.0],   # Set 1: air, air (baseline)
        [2.61417, 4.0],   # Set 2: dry sand, soil
        [3.6659, 6.0],   # Set 3: 7% wet sand, soil
        [9.1372, 22.0],   # Set 4: 22% wet sand, soil
        [27.6485, 26.0],   # Set 5: 30% wet sand, soil
    ]

    all_conductivities = [
        [0, 0],  # Set 1: air, air (baseline)
        [1e-7, 1e-4],  # Set 2: dry sand, soil
        [0.0038, 0.001],  # Set 3: 7% wet sand, soil
        [0.0477,  0.0318 ],  # Set 4: 22% wet sand, soil
        [0.3318,  0.1 ],  # Set 5: 30% wet sand, soil
    ]

    all_lengths = [
        [0.70, 0.05],  # Set 1
        [0.70, 0.05],  # Set 2
        [0.70, 0.05],  # Set 3
        [0.70, 0.05],  # Set 4
        [0.70, 0.05],  # Set 5
    ]

    labels = ["Air/Air", "Dry Sand/Soil", "7% Wet Sand/Soil", "22% Wet Sand/Soil", "30% Wet Sand/Soil"]

    run_validation_sets(all_epsilon_r, all_conductivities, all_lengths, labels)