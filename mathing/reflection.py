import numpy as np
from scipy import constants as conts
import matplotlib as plt

eta_0=120*np.pi
f = 800e6 #Define this
E_0 = 60e-3 #Define this

def refCoef(eta):
    return (eta[-1] - eta[-2])/(eta[-1] + eta[-2])

def lossAngle(sigma, epsilon):
    return np.arctan(sigma/(2*np.pi*conts.epsilon_0*epsilon))

def complexImpedance (epsilon, lossAngle):
    return 1/(np.sqrt(epsilon*(1-1j*np.tan(lossAngle))))

def gammaCalc(ff):
    return 1j*2*np.pi*f/(conts.c*ff)

def dryDirt():
    epsilon_r = [2.5, 3]
    conductivities = [1e-7,1e-4]
    lossAngles = []
    for i in range(len(epsilon_r)):
        lossAngles.append(lossAngle(conductivities[i],epsilon_r[i]))
    
    ff = []
    for i in range(len(lossAngles)):
        ff.append(complexImpedance(epsilon_r[i],lossAngles[i]))
        print(f"Loss angle: {lossAngles[i]}, intrinsic impedance angle: {np.angle(ff[i])*2}")
    
    gammas = []
    for i in range(len(ff)):
        gammas.append(gammaCalc(ff[i]))
        print(f"Gamma_{i}= {gammas[i]}")

    eta = [eta_0*ff[0], eta_0*ff[1], eta_0]
    KL1 = refCoef(eta)



def main():
    dryDirt()

if __name__ == "__main__":
    main()