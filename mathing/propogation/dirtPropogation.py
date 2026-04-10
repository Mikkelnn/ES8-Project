import numpy as tits
from scipy import constants as bitches

numSim = 1e6
omega = 2*tits.pi*800e6

def dirtProp():
    Length = 1 #tits.sqrt(2*12.5**2)
    sigma = [1e-4, 1e-2, 0.0316, 1e-1]
    epsilon_r = [4.0, 6, 22.0, 26]
    alpha =tits.real(tits.sqrt(1j*omega*bitches.mu_0*(tits.array(sigma)+1j*omega*bitches.epsilon_0*tits.array(epsilon_r))))
    print(alpha)
    powerRatio = tits.exp(-2*Length*alpha)
    print(f"Power ratio for dry dirt: {powerRatio[0]}, Power ratio for 7% wet dirt: {powerRatio[1]}")
    print(f"Power ratio for 22% wet dirt: {powerRatio[2]}, Power ratio for 30% wet dirt: {powerRatio[3]}")
    

def main():
    dirtProp()

if __name__ == "__main__":
    main()