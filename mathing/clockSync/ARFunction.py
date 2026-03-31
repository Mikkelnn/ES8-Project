"""
This is a conversion of a stochastic clock model to a linear function, based on the 5th order AR-model by Ha Yang Kim
Paper: "Modelling and tracking time-varying clock drifts in wireless networks"
Link : https://repository.gatech.edu/server/api/core/bitstreams/43896d5a-455e-4cfd-b1f3-79dabf3892a2/content?fbclid=IwY2xjawQt6DlleHRuA2FlbQIxMQBzcnRjBmFwcF9pZAEwAAEeYL88DRMjtDQSufNTukDAubJlwZl5lJgbONxTgMEyxQwzGwBor4SH7HOmlfg_aem_AtC_rb3MnE4wVGpiK14oeQ
"""

import numpy as np
import matplotlib.pyplot as plt


c = np.array([0.92705, 0.4163, 0.07483, -0.387, -0.03118]) #AR-model constants from page 32
x_init = np.array([3.95e-5, 3.95e-5, 3.95e-5, 3.95e-5, 3.95e-5]) #initial conditions for the AR-model. alpha[0] is the variance for the clock skew see page 33
noiseVar = 3.915e-15

def ar5_closed_form(c, x_init):
    """
    Returns a function x(n) for the AR(5) process:
        x_n = c[0] x_{n-1} + ... + c[4] x_{n-5}
    
    Parameters:
        c       : array-like of length 5 (coefficients)
        x_init  : array-like of length 5 ([x0, x1, x2, x3, x4])
    
    Returns:
        function x(n)
    """
    
    # Characteristic polynomial: r^5 - c1 r^4 - ... - c5
    coeffs = [1, -c[0], -c[1], -c[2], -c[3], -c[4]]
    
    # Roots
    roots = np.roots(coeffs)
    
    # Build Vandermonde matrix
    V = np.vander(roots, 5, increasing=True).T
    
    # Solve for coefficients A_i
    A = np.linalg.solve(V, x_init)
    
    # Return function
    def x(n):
        return np.real_if_close(np.sum(A * (roots ** n)))
    
    return x

def impulse_response(c, N):
    """
    Compute psi_k coefficients up to N
    """
    psi = np.zeros(N)
    psi[0] = 1.0
    
    for n in range(1, N):
        psi[n] = sum(c[i] * psi[n-i-1] for i in range(min(n, 5)))
    
    return psi

def variance_over_time(c, sigma2, N):
    psi = impulse_response(c, N)
    
    var = np.zeros(N)
    for n in range(N):
        var[n] = sigma2 * np.sum(psi[:n+1]**2)
    
    return var

def confidence_bands(x_det, var, k=2):
    std = np.sqrt(var)
    upper = x_det + k * std
    lower = x_det - k * std
    return lower, upper


if __name__ == "__main__":
    N = 1000
    x_func = ar5_closed_form(c, x_init)
    n_vals = np.arange(0, N)
    x_vals = np.array([x_func(n) for n in n_vals])
    print(x_vals)
    var = variance_over_time(c, noiseVar, N)
    # print(var)
    lower, upper = confidence_bands(x_vals, var)
    plt.plot(x_vals, label="Deterministic")
    plt.fill_between(n_vals, lower, upper, alpha=0.3, label="95% band")
    plt.legend()
    plt.show()

