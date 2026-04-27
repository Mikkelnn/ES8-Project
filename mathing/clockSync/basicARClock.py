"""
This is a simple clock drift model, based on the 5th order AR-model by Ha Yang Kim
Paper: "Modelling and tracking time-varying clock drifts in wireless networks"
Link : https://repository.gatech.edu/server/api/core/bitstreams/43896d5a-455e-4cfd-b1f3-79dabf3892a2/content?fbclid=IwY2xjawQt6DlleHRuA2FlbQIxMQBzcnRjBmFwcF9pZAEwAAEeYL88DRMjtDQSufNTukDAubJlwZl5lJgbONxTgMEyxQwzGwBor4SH7HOmlfg_aem_AtC_rb3MnE4wVGpiK14oeQ
"""

import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt

np.random.seed(42)


tolerance = 5e-2
meanDrift = 3.95e-5 #np.random.uniform(-tolerance, tolerance)

t0 = 900
c_std = np.array([0.9271, 0.4163, 0.07483, -0.387, -0.03118])*0.98 #AR-model constants from page 32
c_temp = np.array([0.4397, 0.3106, 0.1874])

init_Temp = np.array([0, 1.7e-3, 1.7e-3, 1.7e-3])
init_Temp = np.transpose(init_Temp)

noiseVar = 3.915e-9
noiseVarTemp = 6.9e-10

simLength = 365*4 #days
timeScale = 'Days'
samplesDay = int(24*3600/t0)
k_Temp = 5.559e-6



def plotData(data):
    # Extract theta and alpha values
    theta_values = [point[0] for point in data]
    alpha_values = [point[1] for point in data]
    time_steps = np.arange(len(data)) / 96  # Convert samples to days/minutes (96/60 samples per day/minute)
    
    # Create figure with two subplots
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
    
    # Plot theta (clock drift)
    ax1.plot(time_steps, theta_values, 'b-', linewidth=1.5, label='Clock Drift (θ)')
    ax1.set_xlabel(f'Time ({timeScale})')
    ax1.set_ylabel('Clock Drift (seconds)')
    ax1.set_title('Clock Drift (Theta) over Time')
    ax1.grid(True, alpha=0.3)
    ax1.legend()
    
    # Plot alpha (clock skew)
    ax2.plot(time_steps, alpha_values, 'r-', linewidth=1.5, label='Clock Skew (α)')
    ax2.set_xlabel(f'Time ({timeScale})')
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
        
def plot_psd(w=None, psd=None):
    """
    Plot the Power Spectral Density of the AR model.
    
    Args:
        w: Frequency array (default: np.linspace(0, np.pi, 1024))
        psd: PSD values (default: computed from AR model)
    """
    if w is None or psd is None:
        # Compute PSD if not provided
        w = np.linspace(0, np.pi, 1024)
        den = np.ones_like(w, dtype=complex)
        
        for k, c_stdk in enumerate(c_std, start=1):
            den -= c_stdk * np.exp(-1j * k * w)
        
        psd = noiseVar / np.abs(den)**2
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    ax.semilogy(w, psd, 'b-', linewidth=2)
    ax.set_xlabel('Normalized Frequency (rad/sample)')
    ax.set_ylabel('Power Spectral Density')
    ax.set_title('Power Spectral Density of AR Clock Drift Model')
    ax.grid(True, which='both', alpha=0.3)
    
    plt.tight_layout()
    plt.show()

def plot_multiple_realizations(num_realizations=10):
    """
    Simulate and plot multiple realizations of the AR model on the same plot.
    
    Args:
        num_realizations: Number of realizations to generate and plot
    """
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
    
    for i in range(num_realizations):
        data = ARModelSimple()
        # print(f"Realization {i} clock drift after 100 days: {data[9600][0]}")
        theta_values = [point[0] for point in data]
        alpha_values = [point[1] for point in data]
        time_steps = np.arange(len(data)) / 60  # Convert samples to days/minuttes
        
        ax1.plot(time_steps, theta_values, alpha=0.7, linewidth=1)
        ax2.plot(time_steps, alpha_values, alpha=0.7, linewidth=1)
    
    # Configure theta subplot
    ax1.set_xlabel(f'Time ({timeScale})')
    ax1.set_ylabel('Clock Drift (seconds)')
    ax1.set_title(f'{num_realizations} Clock Drift Realizations')
    ax1.grid(True, alpha=0.3)
    
    # Configure alpha subplot
    ax2.set_xlabel(f'Time ({timeScale})')
    ax2.set_ylabel('Clock Skew (s/s)')
    ax2.set_title(f'{num_realizations} Clock Skew Realizations')
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.show()


def ARModelSimple():
    # meanDrift = np.random.uniform(-tolerance, tolerance)
    # print(f"Mean skew: {meanDrift}")
    # meanDrift = 0

    A = np.array([[1, t0, 0, 0, 0, 0],
         [0, c_std[0], c_std[1], c_std[2], c_std[3], c_std[4]],
         [0, 1, 0, 0, 0, 0],
         [0, 0, 1, 0, 0, 0],
         [0, 0, 0, 1, 0, 0],
         [0, 0, 0, 0, 1, 0]])
    std_dev = np.sqrt(noiseVar)
    z0 = np.random.normal(0, scale=std_dev)  
    w0 = np.array([0, z0, 0, 0, 0, 0]) 
    init = np.array([0, meanDrift, meanDrift, meanDrift, meanDrift, meanDrift])*1.05 #initial conditions for the AR-model. alpha[0] is the variance for the clock skew see page 33
    init = np.transpose(init)

    X = A @ init + np.transpose(w0)
    z = np.random.normal(0, scale=std_dev, size=simLength*96) #96 15 minuttes in a day 
    data = [[X[0], X[1]]]
    meanVector = np.array([0, meanDrift, meanDrift, meanDrift, meanDrift, meanDrift])
    meanVector = np.transpose(meanVector)

    for i in range(len(z)):
        # print(f"Time: {i*t0} seconds\nX vector:\n{X.reshape(-1, 1)}\nnoise: {z[i]}")
        w = np.array([0, z[i], 0, 0, 0, 0])
        w = np.transpose(w)
        X = A @ X + w
        data.append(X[:2])
    # print(data)
    return data

def pipeTemp(n, phi):
    return 10*np.sin(n*2*np.pi/(365*samplesDay) + phi + np.pi) + 66

def groundTemp(n, phi):
    return 8*np.sin(n*2*np.pi/(365*samplesDay) + phi) + 19

def tempModel(start):
    phi = start*np.pi/6 - 2*np.pi/3
    A = np.array([[1, t0, 0, 0],
         [0, c_temp[0], c_temp[1], c_temp[2]],
         [0, 1, 0, 0],
         [0, 0, 1, 0]])
    B = np.array([0, k_Temp, 0, 0])
    B = np.transpose(B)
    std_dev = np.sqrt(noiseVarTemp)
    z0 = np.random.normal(0, scale=std_dev)  
    w0 = np.array([0, z0, 0, 0]) 
    Temp0 = (pipeTemp(0, phi) + groundTemp(0, phi))/2

    X = A @ init_Temp + Temp0*B + w0
    z = np.random.normal(0, scale=std_dev, size=int(simLength*samplesDay)) #96 15 minuttes in a day 
    data = [[X[0], X[1]]]
    for i in range(len(z)):
        Temp = (pipeTemp(i, phi) + groundTemp(i, phi))/2 - 25
        # print(f"Temperature a time {i}: {Temp}, pipeTemp: {pipeTemp(i, phi)}")
        w = np.array([0, z[i], 0, 0])
        w = np.transpose(w)
        X = A @ X + Temp*B + w
        data.append(X[:2])
    # print(data)
    return data


def get_model_state_at_time(time_x, data, time_step_seconds=t0):
    """
    Query the AR model state at a specific time.
    
    Args:
        time_x: The time in seconds to query
        data: The simulation data (list of [theta, alpha] pairs)
        time_step_seconds: Duration of each time step in seconds (default: 900 = 15 minutes)
    
    Returns:
        tuple: (clock_drift, clock_skew) at time_x, or None if out of bounds
    
    Raises:
        ValueError: If time_x is negative or data is empty
    """
    if not data:
        raise ValueError("Data is empty")
    if time_x < 0:
        raise ValueError("Time cannot be negative")
    
    # Convert time in seconds to array index
    time_step_index = int(round(time_x / time_step_seconds))
    
    # Check bounds
    if time_step_index >= len(data):
        print(f"Warning: Requested time {time_x}s is beyond simulation length. "
              f"Max available time: {(len(data)-1) * time_step_seconds}s")
        return None
    
    # Retrieve state at the time step
    state = data[time_step_index]
    clock_drift = state[0]
    clock_skew = state[1]
    
    return clock_drift, clock_skew    
        
def AR1Model():
    VarStd = np.sqrt(noiseVar)
    mean = 0
    c1 = 0.95
    alpha0 = 0
    theta0 = 0
    data = [[theta0, alpha0]]
    for i in range(samplesDay*simLength):
        skew = data[i][1]*c1 + np.random.normal(0, VarStd)
        drift = data[i][0] + t0*(skew + mean)
        data.append([drift, skew])
    return data

def main ():
    # Uncomment the following line to plot a single realization with detailed stats
    AR5data = np.array(ARModelSimple())
    AR1data = np.array(AR1Model())  
    # print(AR5data[:,1])


    # Plot 10 realizations on the same plot
    # plot_multiple_realizations(num_realizations=10)

    #Temperature based drift
    # data = tempModel(start = 1) #Write month number
    # plotData(AR5data)
    # plot_psd()
    analysis(AR1data, AR5data)
    
def analysis(AR1data, AR5data):
    AR5ACF = np.correlate(AR5data[:, 1], AR5data[:, 1], mode = "full")
    AR5ACF = AR5ACF[AR5ACF.size//2:]
    AR5ACF = AR5ACF/AR5ACF[0] #Normalize the ACF

    AR1ACF = np.correlate(AR1data[:, 1], AR1data[:, 1], mode = "full")
    AR1ACF = AR1ACF[AR1ACF.size//2:]
    AR1ACF = AR1ACF/AR1ACF[0] #Normalize the ACF

    # Plot both ACFs on the same figure
    fig, ax = plt.subplots(figsize=(12, 6))
    
    lags = np.arange(20)
    ax.plot(lags, AR5ACF[:20], 'b-', linewidth=2, label='AR5 ACF', alpha=0.7)
    ax.plot(lags, AR1ACF[:20], 'r-', linewidth=2, label='AR1 ACF', alpha=0.7)
    
    ax.set_xlabel('Lag')
    ax.set_ylabel('Autocorrelation')
    ax.set_title('Autocorrelation Functions normalized: AR5 vs AR1')
    # ax.set_yscale('log')
    ax.legend()
    ax.grid(True, alpha=0.3, which='both')
    
    plt.tight_layout()
    plt.show()




if __name__=="__main__":
    main()