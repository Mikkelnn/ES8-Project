import numpy as np
from scipy.optimize import least_squares

c_std = np.array([0.9271, 0.4163, 0.07483, -0.387, -0.03118]) * 0.98
noiseVar = 3.915e-15

def PSD5(w):
    den = np.ones_like(w, dtype=complex)
    for k, c_stdk in enumerate(c_std, start=1):
        den -= c_stdk * np.exp(-1j * k * w)
    return noiseVar / np.abs(den)**2

def PSD1(w, G, C):
    return G * noiseVar / np.abs(1 - C * np.exp(-1j * w))**2

# Frequency grid (dense near 0)
w = np.concatenate([
    np.linspace(1e-4, 0.1, 100),   # dense low freq
    np.linspace(0.1, np.pi, 100)   # rest
])

# Weighting: emphasize low frequencies
weights = 1 / (w + 1e-3)

def residuals(params):
    G, C = params
    
    psd1 = PSD1(w, G, C)
    psd5 = PSD5(w)
    
    # log-domain error (more stable)
    err = np.log(psd1) - np.log(psd5)
    
    return weights * err

# Bounds: enforce stability |C| < 1
bounds = (
    [0, -0.999],   # G > 0, C < 1
    [np.inf, 0.999]
)

result = least_squares(
    residuals,
    x0=[1, 0.5],
    bounds=bounds
)

G_opt, C_opt = result.x
print("G:", G_opt)
print("C:", C_opt)