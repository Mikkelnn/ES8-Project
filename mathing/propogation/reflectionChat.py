import numpy as np
from scipy import constants as conts

# -----------------------
# Constants
# -----------------------
eta0 = 120 * np.pi
f = 800e6
omega = 2 * np.pi * f
c = conts.c
P_in = 10e-3  # 10 mW forward wave in first medium


# -----------------------
# Material Functions
# -----------------------

def loss_tangent(sigma, epsilon_r):
    return sigma / (omega * conts.epsilon_0 * epsilon_r)


def intrinsic_impedance(epsilon_r, tan_delta):
    return eta0 / np.sqrt(epsilon_r * (1 - 1j * tan_delta))


def propagation_constant(epsilon_r, tan_delta):
    return 1j * omega / c * np.sqrt(epsilon_r * (1 - 1j * tan_delta))


# -----------------------
# Characteristic Matrix
# -----------------------

def layer_matrix(gamma, eta, d):
    cosh = np.cosh(gamma * d)
    sinh = np.sinh(gamma * d)

    return np.array([
        [cosh, eta * sinh],
        [sinh / eta, cosh]
    ])


# -----------------------
# Multilayer Solver
# -----------------------

def multilayer_solver(epsilon_r, sigma, thicknesses):

    n_layers = len(epsilon_r)

    # Compute material properties
    tan_d = [loss_tangent(sigma[i], epsilon_r[i]) for i in range(n_layers)]
    eta = [intrinsic_impedance(epsilon_r[i], tan_d[i]) for i in range(n_layers)]
    gamma = [propagation_constant(epsilon_r[i], tan_d[i]) for i in range(n_layers)]

    # Build total transfer matrix
    M_total = np.identity(2, dtype=complex)

    for i in range(n_layers):
        M_i = layer_matrix(gamma[i], eta[i], thicknesses[i])
        M_total = M_total @ M_i

    # Air is output medium
    eta_out = eta0

    M11, M12 = M_total[0]
    M21, M22 = M_total[1]

    # Transmission coefficient
    T = (2 * eta_out) / (
        M11 * eta_out + M12 + M21 * eta_out**2 + M22 * eta_out
    )

    P_out = P_in * np.abs(T)**2

    print("----- Multilayer Results -----")
    print(f"Transmission coefficient: {T}")
    print(f"Output power: {P_out:.6f} W")
    print(f"Efficiency: {100 * P_out / P_in:.2f} %")

    return P_out


# -----------------------
# Example: Sand + Dirt
# -----------------------

if __name__ == "__main__":

    epsilon_r = [2.5, 3.0]     # sand, dirt
    sigma = [1e-7, 1e-4]       # S/m
    thicknesses = [0.7, 0.05]  # meters

    multilayer_solver(epsilon_r, sigma, thicknesses)