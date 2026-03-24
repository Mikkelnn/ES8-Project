"""
This is a simple clock drift model, based on the 5th order AR-model by Ha Yang Kim
Paper: "Modelling and tracking time-varying clock drifts in wireless networks"
Link : https://repository.gatech.edu/server/api/core/bitstreams/43896d5a-455e-4cfd-b1f3-79dabf3892a2/content?fbclid=IwY2xjawQt6DlleHRuA2FlbQIxMQBzcnRjBmFwcF9pZAEwAAEeYL88DRMjtDQSufNTukDAubJlwZl5lJgbONxTgMEyxQwzGwBor4SH7HOmlfg_aem_AtC_rb3MnE4wVGpiK14oeQ
"""

import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt

t0 = 900
c = np.array([0.92705001, 0.4163, 0.07483, -0.387, -0.03118]) #AR-model constants from page 32
init = np.array([0, 3.95e-5, 3.95e-5, 3.95e-5, 3.95e-5, 3.95e-5]) #initial conditions for the AR-model. alpha[0] is the variance for the clock skew see page 33
init = np.transpose(init)
noiseVar = 3.915e-15
simLength = 4000 #days


def plotData(data):
    # Extract theta and alpha values
    theta_values = [point[0] for point in data]
    alpha_values = [point[1] for point in data]
    time_steps = np.arange(len(data))
    
    # Create figure with two subplots
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
    
    # Plot theta (clock drift)
    ax1.plot(time_steps, theta_values, 'b-', linewidth=1.5, label='Clock Drift (θ)')
    ax1.set_xlabel('Time Step (15 min intervals)')
    ax1.set_ylabel('Clock Drift (seconds)')
    ax1.set_title('Clock Drift (Theta) over Time')
    ax1.grid(True, alpha=0.3)
    ax1.legend()
    
    # Plot alpha (clock skew)
    ax2.plot(time_steps, alpha_values, 'r-', linewidth=1.5, label='Clock Skew (α)')
    ax2.set_xlabel('Time Step (15 min intervals)')
    ax2.set_ylabel('Clock Skew (s/s)')
    ax2.set_title('Clock Skew (Alpha) over Time')
    ax2.grid(True, alpha=0.3)
    ax2.legend()
    
    plt.tight_layout()
    plt.show()
    
    # Print summary statistics
    print(f"\nSummary Statistics:")
    print(f"Theta (Clock Drift):")
    print(f"  Min: {min(theta_values):.6e}")
    print(f"  Max: {max(theta_values):.6e}")
    print(f"  Mean: {np.mean(theta_values):.6e}")
    print(f"  Std Dev: {np.std(theta_values):.6e}")
    print(f"\nAlpha (Clock Skew):")
    print(f"  Min: {min(alpha_values):.6e}")
    print(f"  Max: {max(alpha_values):.6e}")
    print(f"  Mean: {np.mean(alpha_values):.6e}")
    print(f"  Std Dev: {np.std(alpha_values):.6e}")
        


def ARModelSimple():
    A = np.array([[1, t0, 0, 0, 0, 0],
         [0, c[0], c[1], c[2], c[3], c[4]],
         [0, 1, 0, 0, 0, 0],
         [0, 0, 1, 0, 0, 0],
         [0, 0, 0, 1, 0, 0],
         [0, 0, 0, 0, 1, 0]])
    std_dev = np.sqrt(noiseVar)
    z0 = np.random.normal(0, scale=std_dev)  
    w0 = np.array([0, z0, 0, 0, 0, 0]) 
    X = A @ init + w0
    z = np.random.normal(0, scale=std_dev, size=simLength*96) #96 15 minuttes in a day 
    data = [[X[0], X[1]]]
    for i in range(len(z)):
        # print(f"Time: {i*t0} seconds\nX vector:\n{X.reshape(-1, 1)}\nnoise: {z[i]}")
        w = np.array([0, z[i], 0, 0, 0, 0])
        w = np.transpose(w)
        X = A @ X + w
        data.append(X[:2])
    # print(data)
    plotData(data)
    

        
        
    

def main ():
    ARModelSimple()

if __name__=="__main__":
    main()