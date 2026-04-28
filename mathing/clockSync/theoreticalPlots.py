import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import freqz

# Your AR(5) coefficients
phi5 = 0.98 * np.array([0.9271, 0.4163, 0.07483, -0.387, -0.03118])

# AR(1) coefficient (from earlier result)
phi1 = np.array([0.90])  # you can refine this if needed

def theoretical_acf_ar(phi, nlags=50):
    p = len(phi)
    
    # Build Yule-Walker system for rho(1)...rho(p)
    A = np.zeros((p, p))
    b = np.zeros(p)
    
    for i in range(p):
        b[i] = phi[i]
        for j in range(p):
            if i == j:
                A[i, j] = 1
            if (i - j - 1) >= 0:
                A[i, j] -= phi[i - j - 1]
            if (j - i - 1) >= 0:
                A[i, j] -= phi[j - i - 1]
    
    rho_init = np.linalg.solve(A, b)
    
    # Full ACF
    rho = np.zeros(nlags)
    rho[0] = 1
    rho[1:p+1] = rho_init
    
    # Recursion
    for k in range(p+1, nlags):
        rho[k] = np.dot(phi, rho[k-1:k-p-1:-1])
    
    return rho

acf_ar5 = theoretical_acf_ar(phi5, nlags=100)
acf_ar1 = theoretical_acf_ar(phi1, nlags=100)

def ar_psd(phi, nfft=512, sigma2=1.0):
    # AR polynomial: 1 - phi1 z^-1 - ...
    a = np.concatenate(([1], -phi))
    
    w, h = freqz([1], a, worN=nfft)
    psd = sigma2 * np.abs(h)**2
    
    return w, psd

w5, psd_ar5 = ar_psd(phi5)
w1, psd_ar1 = ar_psd(phi1)

plt.figure()
plt.plot(acf_ar5, label='AR(5)')
plt.plot(acf_ar1, '--', label='AR(1)')
plt.title("Autocorrelation Function")
plt.xlabel("Lag")
plt.ylabel("ACF")
plt.legend()
plt.grid()

plt.figure()
plt.plot(w5, 10*np.log10(psd_ar5), label='AR(5)')
plt.plot(w1, 10*np.log10(psd_ar1), '--', label='AR(1)')
plt.title("Power Spectral Density")
plt.xlabel("Frequency (rad/sample)")
plt.ylabel("Power (dB)")
plt.legend()
plt.grid()

plt.show()