import numpy as np
from scipy import constants as consts

numSim = 1e6
omega = 2*np.pi*800e6

def dirtProp():
    Length = np.sqrt(2*12.5**2)
    sigma = [1e-4, 1e-2, 0.0316, 1e-1, 5e-2]
    epsilon_r = [4.0, 6, 22.0, 26, 78.4]
    alpha =np.real(np.sqrt(1j*omega*consts.mu_0*(np.array(sigma)+1j*omega*consts.epsilon_0*np.array(epsilon_r))))
    print(alpha)
    powerRatio = np.exp(-2*Length*alpha)
    print(f"Power ratio for dry dirt: {10*np.log10(powerRatio[0])} dB, Power ratio for 7% wet dirt: {10*np.log10(powerRatio[1])} dB")
    print(f"Power ratio for 22% wet dirt: {10*np.log10(powerRatio[2])} dB, Power ratio for 30% wet dirt: {10*np.log10(powerRatio[3])} dB")
    print(f"Power ratio for pure drinking water: {10*np.log10(powerRatio[4])} dB")
    

def main():
    dirtProp()

if __name__ == "__main__":
    main()