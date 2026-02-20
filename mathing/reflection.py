import numpy as np
from scipy import constants as conts
import matplotlib as plt

eta_0=120*np.pi
f = 800e6 #Define this
E_0 = 60e-3 #Define this

def refCoef(eta):
    return (eta[-1] - eta[-2])/(eta[-1] + eta[-2])

def lossAngle(sigma, epsilon):
    return sigma/(2*np.pi*f*conts.epsilon_0*epsilon)

def complexImpedance (epsilon, lossAngle):
    return 1/(np.sqrt(epsilon*(1-1j*lossAngle)))

def gammaCalc(ff):
    return 1j*2*np.pi*f/(conts.c*ff)

def refCoefLen(KL, gamma, length):
    return KL*np.exp(-2*gamma*length)

def inputImpedance(eta, Kminus):
    return eta*(1-Kminus)/(1+Kminus)

def EplusNext(KL, KminusL, Eplus):
    Etot1 = Eplus*(1+KL)
    print(f"Total E-field at boundary: {Etot1}")
    return Etot1/(1+KminusL)

def firstMediumLoss(gamma, Length):
    return E_0*np.exp(-gamma*Length)

def dryDirt():
    epsilon_r = [2.5, 3]
    conductivities = [1e-7,1e-4] #in S/m
    lengths = [0.7, 0.05] #in meters
    lossAngles = []
    for i in range(len(epsilon_r)):
        lossAngles.append(lossAngle(conductivities[i],epsilon_r[i]))
    
    ff = []
    for i in range(len(lossAngles)):
        ff.append(complexImpedance(epsilon_r[i],lossAngles[i]))
        print(f"Loss angle: {np.arctan(lossAngles[i])}, intrinsic impedance angle: {np.angle(ff[i])*2}")
    
    gammas = []
    for i in range(len(ff)):
        gammas.append(gammaCalc(ff[i]))
        print(f"Gamma_{i}= {gammas[i]}")

    eta = [eta_0*ff[0], eta_0*ff[1], eta_0]
    KL1 = refCoef(eta)
    KminusL = refCoefLen(KL1, gammas[1], lengths[1])
    eta2in = inputImpedance(eta[1], KminusL)
    KL2 = refCoef([eta[0],eta2in])
    print(f"Reflection coeffecient at first boundary: {KL2}")

    EPlus1 = firstMediumLoss(gammas[0], lengths[0])
    EPlus2 = EplusNext(KL2, KminusL, EPlus1)
    ETotAir = np.abs(EPlus2*(1+KL1))
    print(f"E+ at first boundary: {EPlus1}, E+ at second boundary: {EPlus2}, total E-field in the air: {ETotAir}")




def main():
    dryDirt()

if __name__ == "__main__":
    main()