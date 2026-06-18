"""
This is a simple clock drift model, based on the 5th order AR-model by Ha Yang Kim
Paper: "Modelling and tracking time-varying clock drifts in wireless networks"
Link : https://repository.gatech.edu/server/api/core/bitstreams/43896d5a-455e-4cfd-b1f3-79dabf3892a2/content?fbclid=IwY2xjawQt6DlleHRuA2FlbQIxMQBzcnRjBmFwcF9pZAEwAAEeYL88DRMjtDQSufNTukDAubJlwZl5lJgbONxTgMEyxQwzGwBor4SH7HOmlfg_aem_AtC_rb3MnE4wVGpiK14oeQ
"""

import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt

seed = 42


tolerance = 5e-2
meanDrift = 0 #np.random.uniform(-tolerance, tolerance)

t0 = 60
c_std = np.array([0.9271, 0.4163, 0.07483, -0.387, -0.03118])*0.98 #AR-model constants from page 32
c_temp = np.array([0.4397, 0.3106, 0.1874])

init_Temp = np.array([0, 1.7e-3, 1.7e-3, 1.7e-3])
init_Temp = np.transpose(init_Temp)

noiseVar = 3.915e-15
noiseVarTemp = 6.9e-10

simLength = 365*4 #days
timeScale = 'Samples'
samplesDay = int(24*3600/t0)
k_Temp = 5.559e-6
smallSamples = 5000

AR1Const = 0.9087642375247008
AR1Gain = 20.970167331917025

def plotData(data):
    # Extract theta and alpha values
    theta_values = [point[0] for point in data]
    alpha_values = [point[1] for point in data]
    time_steps = np.arange(len(data))  # Convert samples to days/minutes (96/60 samples per day/minute)

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
        w = np.linspace(-np.pi, np.pi, 2048)
        den = np.ones_like(w, dtype=complex)
        
        for k, c_stdk in enumerate(c_std, start=1):
            den -= c_stdk * np.exp(-1j * k * w)
        
        psdAR5 = noiseVar / np.abs(den)**2
        den2 = np.ones_like(w, dtype=complex)
        den2 -= AR1Const*np.exp(-1j * w) 
        psdAR1 = noiseVar* AR1Gain/np.abs(den2)**2
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    ax.semilogy(w, psdAR5, 'b-', label = "AR5PSD", linewidth=2)
    ax.semilogy(w, psdAR1, 'r-', label = "AR1PSD", linewidth=2)
    ax.set_xlabel('Normalized Frequency (rad/sample)')
    ax.set_ylabel('Power Spectral Density')
    ax.set_title('Power Spectral Density of AR Clock Drift Model')
    ax.legend()
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
    np.random.seed(seed)
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
    init = np.array([0, meanDrift, meanDrift, meanDrift, meanDrift, meanDrift]) #initial conditions for the AR-model. alpha[0] is the variance for the clock skew see page 33
    init = np.transpose(init)

    X = A @ init + np.transpose(w0)
    z = np.random.normal(0, scale=std_dev, size=smallSamples) #96 15 minuttes in a day 
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
        
def AR1Model(trend_rate=0.0):
    """
    AR1 clock drift model with optional linear trend.
    
    Args:
        trend_rate: Linear trend in seconds per second (default: 0.0)
                   E.g., 4e-5 means 40 microseconds per second drift
    """
    np.random.seed(seed)
    VarStd = np.sqrt(noiseVar*AR1Gain) 
    mean = 0
    c1 = AR1Const
    alpha0 = 0
    theta0 = 0
    data = [[theta0, alpha0]]
    
    # Trend contribution per time step (in seconds)
    trend_per_step = trend_rate * t0
    
    for i in range(smallSamples):
        skew = data[i][1]*c1 + np.random.normal(0, VarStd)
        # Drift includes both the AR1 contribution and the linear trend
        drift = data[i][0] + t0*(skew + mean) + trend_per_step
        data.append([drift, skew])
    return data


class KalmanFilterAR1:
    """
    Kalman filter for AR1 clock drift model.
    
    State: [theta, alpha]^T where theta is clock drift, alpha is clock skew
    Dynamics: 
        alpha[n+1] = c1 * alpha[n] + w_process
        theta[n+1] = theta[n] + t0 * alpha[n+1] + w_process
    Measurement: Direct observation of [theta, alpha] with noise
    """
    
    def __init__(self, process_noise_var, measurement_noise_var, c1=AR1Const, t0_val=t0):
        """
        Initialize Kalman filter parameters.
        
        Args:
            process_noise_var: Process noise variance (variance in alpha noise)
            measurement_noise_var: Measurement noise variance
            c1: AR1 constant (default: AR1Const)
            t0_val: Time step in seconds (default: t0)
        
        Note:
            The process noise is correlated because:
            alpha[n+1] = c1*alpha[n] + v_alpha[n]
            theta[n+1] = theta[n] + t0*alpha[n+1] = theta[n] + t0*c1*alpha[n] + t0*v_alpha[n]
            
            So the noise vector w = [t0*v_alpha, v_alpha]^T has covariance:
            Q = [[t0^2*var, t0*var],
                 [t0*var, var]]
        """
        self.c1 = c1
        self.t0_val = t0_val
        self.process_noise_var = process_noise_var
        self.measurement_noise_var = measurement_noise_var
        
        # State transition matrix
        # alpha[n+1] = c1*alpha[n]
        # theta[n+1] = theta[n] + t0*alpha[n+1] = theta[n] + t0*c1*alpha[n]
        self.F = np.array([[1, t0_val * c1],
                          [0, c1]])
        
        # Measurement matrix (we observe both theta and alpha)
        self.H = np.array([[1, 0],
                          [0, 1]])
        
        # Process noise covariance with correlation term
        # The noise in theta comes from the noise in alpha: w_theta = t0*w_alpha
        # This creates correlation between the process noise terms
        self.Q = np.array([[process_noise_var * (t0_val**2), process_noise_var * t0_val],
                          [process_noise_var * t0_val, process_noise_var]])
        
        # Measurement noise covariance
        self.R = np.array([[measurement_noise_var, 0],
                          [0, measurement_noise_var]])
        
        # Initialize state estimate and covariance
        self.x = np.array([0.0, 0.0])  # [theta, alpha]
        self.P = np.array([[1e-6, 0],
                          [0, 1e-6]])
    
    def predict(self):
        """Prediction step of Kalman filter."""
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q
    
    def update(self, z):
        """
        Update step of Kalman filter.
        
        Args:
            z: Measurement vector [theta, alpha]
        """
        z = np.array(z)
        
        # Innovation (measurement residual)
        y = z - self.H @ self.x
        
        # Innovation covariance
        S = self.H @ self.P @ self.H.T + self.R
        
        # Kalman gain
        K = self.P @ self.H.T @ np.linalg.inv(S)
        
        # Update state estimate
        self.x = self.x + K @ y
        
        # Update covariance estimate
        I = np.eye(2)
        self.P = (I - K @ self.H) @ self.P
    
    def filter_data(self, measurements):
        """
        Filter a sequence of measurements.
        
        Args:
            measurements: List of [theta, alpha] measurements
            
        Returns:
            List of filtered state estimates [[theta, alpha], ...]
        """
        filtered_states = []
        
        for measurement in measurements:
            self.predict()
            self.update(measurement)
            filtered_states.append(self.x.copy())
        
        return filtered_states
    
    def filter_data_sparse(self, full_trajectory, measurement_interval=120):
        """
        Filter trajectory with sparse measurements (every measurement_interval samples).
        
        Between measurement times, only prediction steps are performed.
        At measurement times, we update with the observed accumulated clock drift.
        
        Args:
            full_trajectory: List of [theta, alpha] true values for all samples
            measurement_interval: Number of samples between measurements (default: 50)
            
        Returns:
            Tuple of (filtered_states, prediction_states)
                - filtered_states: State estimates at all time steps (after updates when available)
                - prediction_states: Pure prediction estimates (before updates at measurement times)
        """
        filtered_states = []
        prediction_states = []
        
        for k, true_state in enumerate(full_trajectory):
            # Perform prediction step
            self.predict()
            prediction_states.append(self.x.copy())
            
            # Update only at measurement times
            if (k + 1) % measurement_interval == 0:
                # Measurement: accumulated clock drift (theta) at this time
                z = np.array([true_state[0], true_state[1]])  # Observe both theta and alpha
                self.update(z)
            
            filtered_states.append(self.x.copy())
        
        return filtered_states, prediction_states


def apply_kalman_filter_to_AR1_sparse(AR1_data, process_noise_scale=1.0, measurement_noise_scale=1.0, measurement_interval=50):
    """
    Apply Kalman filter to AR1 model data with sparse measurements.
    
    Measurements (observations) are only available every measurement_interval samples.
    Between measurements, the filter performs prediction only.
    
    Args:
        AR1_data: Raw AR1 model data (full trajectory)
        process_noise_scale: Scale factor for process noise (default: 1.0)
        measurement_noise_scale: Scale factor for measurement noise (default: 1.0)
        measurement_interval: Samples between measurements (default: 50)
        
    Returns:
        Tuple of (filtered_data, prediction_data)
            - filtered_data: Filtered estimates at all time steps
            - prediction_data: Pure predictions (before updates)
    """
    kf = KalmanFilterAR1(
        process_noise_var=noiseVar * AR1Gain * process_noise_scale,
        measurement_noise_var=noiseVar * AR1Gain * measurement_noise_scale
    )
    
    filtered_data, prediction_data = kf.filter_data_sparse(AR1_data, measurement_interval)
    return np.array(filtered_data), np.array(prediction_data)


def apply_kalman_filter_to_AR1(AR1_data, process_noise_scale=1.0, measurement_noise_scale=1.0):
    """
    Apply Kalman filter to AR1 model data.
    
    Args:
        AR1_data: Raw AR1 model data
        process_noise_scale: Scale factor for process noise (default: 1.0)
        measurement_noise_scale: Scale factor for measurement noise (default: 1.0)
        
    Returns:
        Filtered state estimates
    """
    kf = KalmanFilterAR1(
        process_noise_var=noiseVar * AR1Gain * process_noise_scale,
        measurement_noise_var=noiseVar * AR1Gain * measurement_noise_scale
    )
    
    filtered_data = kf.filter_data(AR1_data)
    return np.array(filtered_data)


class KalmanFilterAR1Trend:
    """
    3-state Kalman filter for AR1 clock drift model with trend.
    
    State: [theta, alpha, trend]^T where:
        - theta is accumulated clock drift (seconds)
        - alpha is clock skew (s/s)
        - trend is linear clock drift rate (s/s)
    
    Dynamics:
        alpha[n+1] = c1 * alpha[n] + w_alpha
        theta[n+1] = theta[n] + t0 * alpha[n+1] + t0 * trend[n] + w_theta
        trend[n+1] = trend[n] (constant trend)
    
    Measurement: Observation of [theta, alpha] (trend is estimated)
    """
    
    def __init__(self, process_noise_var, measurement_noise_var, c1=AR1Const, t0_val=t0):
        """
        Initialize 3-state Kalman filter with trend.
        
        Args:
            process_noise_var: Process noise variance (variance in alpha noise)
            measurement_noise_var: Measurement noise variance
            c1: AR1 constant (default: AR1Const)
            t0_val: Time step in seconds (default: t0)
        """
        self.c1 = c1
        self.t0_val = t0_val
        self.process_noise_var = process_noise_var
        self.measurement_noise_var = measurement_noise_var
        
        # State transition matrix (3x3)
        # theta[k+1] = theta[k] + t0*c1*alpha[k] + t0*trend[k]
        # alpha[k+1] = c1*alpha[k]
        # trend[k+1] = trend[k]
        self.F = np.array([[1, t0_val * c1, t0_val],
                          [0, c1, 0],
                          [0, 0, 1]])
        
        # Measurement matrix (1x3) - observe ONLY theta (accumulated drift)
        # Alpha (clock skew) and trend are estimated, not measured
        self.H = np.array([[1, 0, 0]])
        
        # Process noise covariance (3x3)
        # Only alpha has process noise; theta and trend noise comes from alpha
        self.Q = np.array([[process_noise_var * (t0_val**2), process_noise_var * t0_val, 0],
                          [process_noise_var * t0_val, process_noise_var, 0],
                          [0, 0, 0]])  # Trend has no process noise (constant)
        
        # Measurement noise covariance (1x1) - only for theta measurement
        self.R = np.array([[measurement_noise_var]])
        
        # Initialize state estimate and covariance
        self.x = np.array([0.0, 0.0, 0.0])  # [theta, alpha, trend]
        self.P = np.array([[1e-6, 0, 0],
                          [0, 1e-6, 0],
                          [0, 0, 1e-4]])  # Higher initial uncertainty on trend
    
    def predict(self):
        """Prediction step of 3-state Kalman filter."""
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q
    
    def update(self, z):
        """
        Update step of Kalman filter.
        
        Args:
            z: Measurement scalar (only theta - accumulated clock drift)
        """
        z = np.array([z])  # Convert scalar to 1-element array
        
        # Innovation (measurement residual)
        y = z - self.H @ self.x
        
        # Innovation covariance
        S = self.H @ self.P @ self.H.T + self.R
        
        # Kalman gain
        K = self.P @ self.H.T @ np.linalg.inv(S)
        
        # Update state estimate
        self.x = self.x + K @ y
        
        # Update covariance estimate
        I = np.eye(3)
        self.P = (I - K @ self.H) @ self.P
    
    def filter_data_sparse(self, full_trajectory, measurement_interval=120):
        """
        Filter trajectory with sparse measurements using 3-state model.
        
        Args:
            full_trajectory: List of [theta, alpha] true values for all samples
            measurement_interval: Number of samples between measurements (default: 50)
            
        Returns:
            Tuple of (filtered_states, prediction_states)
        """
        filtered_states = []
        prediction_states = []
        
        for k, true_state in enumerate(full_trajectory):
            # Perform prediction step
            self.predict()
            prediction_states.append(self.x.copy())
            
            # Update only at measurement times (observe only theta, estimate alpha)
            if (k + 1) % measurement_interval == 0:
                z = true_state[0]  # Measure only accumulated drift (theta)
                self.update(z)
            
            filtered_states.append(self.x.copy())
        
        return filtered_states, prediction_states


def apply_kalman_filter_to_AR1_sparse_with_trend(AR1_data, process_noise_scale=1.0, measurement_noise_scale=1.0, measurement_interval=120):
    """
    Apply 3-state Kalman filter (with trend estimation) to AR1 model data with sparse measurements.
    
    Args:
        AR1_data: Raw AR1 model data (full trajectory)
        process_noise_scale: Scale factor for process noise (default: 1.0)
        measurement_noise_scale: Scale factor for measurement noise (default: 1.0)
        measurement_interval: Samples between measurements (default: 50)
        
    Returns:
        Tuple of (filtered_data, prediction_data)
            - filtered_data: Filtered state estimates [theta, alpha, trend] at all time steps
            - prediction_data: Pure prediction estimates at all time steps
    """
    kf = KalmanFilterAR1Trend(
        process_noise_var=noiseVar * AR1Gain * process_noise_scale,
        measurement_noise_var=noiseVar * AR1Gain * measurement_noise_scale
    )
    
    filtered_data, prediction_data = kf.filter_data_sparse(AR1_data, measurement_interval)
    return np.array(filtered_data), np.array(prediction_data)


def plot_AR1_with_kalman(AR1_data, filtered_data=None):
    """
    Plot AR1 model data with optional Kalman filtered overlay.
    
    Args:
        AR1_data: Raw AR1 model data (list or array of [theta, alpha] pairs)
        filtered_data: Filtered data from Kalman filter (optional)
    """
    AR1_data = np.array(AR1_data)
    
    # Extract raw data
    raw_theta = AR1_data[:, 0]
    raw_alpha = AR1_data[:, 1]
    time_steps = np.arange(len(AR1_data))
    
    # Create figure
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))
    
    # Plot theta (clock drift)
    ax1.plot(time_steps, raw_theta, 'r-', linewidth=2, label='AR1 Raw', alpha=0.7)
    if filtered_data is not None:
        filtered_theta = filtered_data[:, 0]
        ax1.plot(time_steps, filtered_theta, 'b-', linewidth=2, label='Kalman Filtered', alpha=0.7)
    ax1.set_xlabel(f'Time ({timeScale})')
    ax1.set_ylabel('Clock Drift (seconds)')
    ax1.set_title('Clock Drift: AR1 vs Kalman Filter')
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc='best')
    
    # Plot alpha (clock skew)
    ax2.plot(time_steps, raw_alpha, 'r-', linewidth=2, label='AR1 Raw', alpha=0.7)
    if filtered_data is not None:
        filtered_alpha = filtered_data[:, 0]
        ax2.plot(time_steps, filtered_alpha, 'b-', linewidth=2, label='Kalman Filtered', alpha=0.7)
    ax2.set_xlabel(f'Time ({timeScale})')
    ax2.set_ylabel('Clock Skew (s/s)')
    ax2.set_title('Clock Skew: AR1 vs Kalman Filter')
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc='best')
    
    plt.tight_layout()
    plt.show()


def compare_AR1_and_kalman(AR1_data, filtered_data):
    """
    Compare AR1 raw data with Kalman filtered data.
    
    Args:
        AR1_data: Raw AR1 model data
        filtered_data: Kalman filtered data
    """
    AR1_data = np.array(AR1_data)
    filtered_data = np.array(filtered_data)
    
    raw_theta = AR1_data[:, 0]
    raw_alpha = AR1_data[:, 1]
    
    filt_theta = filtered_data[:, 0]
    filt_alpha = filtered_data[:, 1]
    
    # Calculate differences (smoothing effect)
    theta_diff = raw_theta - filt_theta
    alpha_diff = raw_alpha - filt_alpha
    
    # Calculate statistics
    print("\n=== Kalman Filter Comparison ===")
    print("\nClock Drift (Theta):")
    print(f"  Raw - Min: {np.min(raw_theta):.6e}, Max: {np.max(raw_theta):.6e}, "
          f"Std: {np.std(raw_theta):.6e}")
    print(f"  Filtered - Min: {np.min(filt_theta):.6e}, Max: {np.max(filt_theta):.6e}, "
          f"Std: {np.std(filt_theta):.6e}")
    print(f"  Difference - Std: {np.std(theta_diff):.6e}")
    
    print("\nClock Skew (Alpha):")
    print(f"  Raw - Min: {np.min(raw_alpha):.6e}, Max: {np.max(raw_alpha):.6e}, "
          f"Std: {np.std(raw_alpha):.6e}")
    print(f"  Filtered - Min: {np.min(filt_alpha):.6e}, Max: {np.max(filt_alpha):.6e}, "
          f"Std: {np.std(filt_alpha):.6e}")
    print(f"  Difference - Std: {np.std(alpha_diff):.6e}")
    
    # Create comparison plot
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    time_steps = np.arange(len(AR1_data))
    
    # Theta comparison
    axes[0, 0].plot(time_steps, raw_theta, 'r-', linewidth=2, label='Raw AR1', alpha=0.7)
    axes[0, 0].plot(time_steps, filt_theta, 'b-', linewidth=2, label='Kalman Filtered', alpha=0.7)
    axes[0, 0].set_ylabel('Clock Drift (seconds)')
    axes[0, 0].set_title('Clock Drift Comparison')
    axes[0, 0].legend()
    axes[0, 0].grid(True, alpha=0.3)
    
    # Alpha comparison
    axes[0, 1].plot(time_steps, raw_alpha, 'r-', linewidth=2, label='Raw AR1', alpha=0.7)
    axes[0, 1].plot(time_steps, filt_alpha, 'b-', linewidth=2, label='Kalman Filtered', alpha=0.7)
    axes[0, 1].set_ylabel('Clock Skew (s/s)')
    axes[0, 1].set_title('Clock Skew Comparison')
    axes[0, 1].legend()
    axes[0, 1].grid(True, alpha=0.3)
    
    # Theta residuals
    axes[1, 0].plot(time_steps, theta_diff, 'g-', linewidth=2, alpha=0.7)
    axes[1, 0].set_xlabel(f'Time ({timeScale})')
    axes[1, 0].set_ylabel('Difference (seconds)')
    axes[1, 0].set_title('Clock Drift Residuals (Raw - Filtered)')
    axes[1, 0].grid(True, alpha=0.3)
    
    # Alpha residuals
    axes[1, 1].plot(time_steps, alpha_diff, 'g-', linewidth=2, alpha=0.7)
    axes[1, 1].set_xlabel(f'Time ({timeScale})')
    axes[1, 1].set_ylabel('Difference (s/s)')
    axes[1, 1].set_title('Clock Skew Residuals (Raw - Filtered)')
    axes[1, 1].grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.show()

def compare_AR1_sparse_kalman_3state(AR1_data, filtered_data, prediction_data, measurement_interval=50, true_trend=0.0):
    """
    Compare AR1 raw data with 3-state sparse-measurement Kalman filtered data.
    
    Args:
        AR1_data: Raw AR1 model data (true trajectory) - [theta, alpha] pairs
        filtered_data: 3-state Kalman filtered estimates - [theta, alpha, trend]
        prediction_data: 3-state prediction estimates - [theta, alpha, trend]
        measurement_interval: Samples between measurements
        true_trend: True trend rate for reference (seconds per second)
    """
    AR1_data = np.array(AR1_data)
    filtered_data = np.array(filtered_data)
    prediction_data = np.array(prediction_data)
    
    raw_theta = AR1_data[:, 0]
    raw_alpha = AR1_data[:, 1]
    
    filt_theta = filtered_data[:, 0]
    filt_alpha = filtered_data[:, 1]
    filt_trend = filtered_data[:, 2]
    
    pred_theta = prediction_data[:, 0]
    pred_alpha = prediction_data[:, 1]
    pred_trend = prediction_data[:, 2]
    
    # Calculate differences
    filt_theta_diff = raw_theta - filt_theta
    pred_theta_diff = raw_theta - pred_theta
    filt_alpha_diff = raw_alpha - filt_alpha
    pred_alpha_diff = raw_alpha - pred_alpha
    
    # Calculate statistics
    print("\n=== 3-State Kalman Filter Comparison (with Trend Estimation) ===")
    print(f"Measurement Interval: {measurement_interval} samples")
    print(f"True Trend Rate: {true_trend:.6e} s/s ({true_trend*1e6:.3f} µs/s)")
    print(f"Filtered Trend (final): {filt_trend[-1]:.6e} s/s ({filt_trend[-1]*1e6:.3f} µs/s)")
    print(f"Predicted Trend (final): {pred_trend[-1]:.6e} s/s ({pred_trend[-1]*1e6:.3f} µs/s)")
    
    print("\nClock Drift (Theta):")
    print(f"  Raw - Std: {np.std(raw_theta):.6e}")
    print(f"  Filtered - Std: {np.std(filt_theta):.6e}")
    print(f"  Prediction Only - Std: {np.std(pred_theta):.6e}")
    print(f"  Filtered Error - Std: {np.std(filt_theta_diff):.6e}")
    print(f"  Prediction Error - Std: {np.std(pred_theta_diff):.6e}")
    
    print("\nClock Skew (Alpha):")
    print(f"  Raw - Std: {np.std(raw_alpha):.6e}")
    print(f"  Filtered - Std: {np.std(filt_alpha):.6e}")
    print(f"  Prediction Only - Std: {np.std(pred_alpha):.6e}")
    print(f"  Filtered Error - Std: {np.std(filt_alpha_diff):.6e}")
    print(f"  Prediction Error - Std: {np.std(pred_alpha_diff):.6e}")
    
    print("\nTrend Estimation:")
    print(f"  Filtered Trend Mean: {np.mean(filt_trend[-1000:]):.6e} s/s (last 1000 samples)")
    print(f"  Trend Convergence: {np.std(filt_trend[-1000:]):.6e} s/s (last 1000 samples std)")
    
    # Create comparison plot
    fig, axes = plt.subplots(3, 2, figsize=(18, 12))
    time_steps = np.arange(len(AR1_data))
    
    # Measurement time steps
    meas_times = np.arange(measurement_interval - 1, len(AR1_data), measurement_interval)
    
    # Theta comparison
    axes[0, 0].plot(time_steps, raw_theta, 'k-', linewidth=1, label='True', alpha=0.6)
    axes[0, 0].plot(time_steps, filt_theta, 'b-', linewidth=1.5, label='Filtered (with trend)', alpha=0.7)
    axes[0, 0].plot(time_steps, pred_theta, 'r--', linewidth=1.5, label='Prediction only', alpha=0.7)
    axes[0, 0].scatter(meas_times, raw_theta[meas_times], color='green', s=20, label='Measurements', zorder=5)
    axes[0, 0].set_ylabel('Clock Drift (seconds)')
    axes[0, 0].set_title('Clock Drift: True vs Filtered vs Prediction')
    axes[0, 0].legend()
    axes[0, 0].grid(True, alpha=0.3)
    
    # Alpha comparison
    axes[0, 1].plot(time_steps, raw_alpha, 'k-', linewidth=1, label='True', alpha=0.6)
    axes[0, 1].plot(time_steps, filt_alpha, 'b-', linewidth=1.5, label='Filtered', alpha=0.7)
    axes[0, 1].plot(time_steps, pred_alpha, 'r--', linewidth=1.5, label='Prediction only', alpha=0.7)
    axes[0, 1].scatter(meas_times, raw_alpha[meas_times], color='green', s=20, zorder=5)
    axes[0, 1].set_ylabel('Clock Skew (s/s)')
    axes[0, 1].set_title('Clock Skew: True vs Filtered vs Prediction')
    axes[0, 1].legend()
    axes[0, 1].grid(True, alpha=0.3)
    
    # Theta errors
    axes[1, 0].plot(time_steps, filt_theta_diff, 'b-', linewidth=1.5, label='Filtered Error', alpha=0.7)
    axes[1, 0].plot(time_steps, pred_theta_diff, 'r--', linewidth=1.5, label='Prediction Error', alpha=0.7)
    axes[1, 0].axhline(y=0, color='k', linestyle='-', linewidth=0.5, alpha=0.3)
    axes[1, 0].set_ylabel('Error (seconds)')
    axes[1, 0].set_title('Clock Drift Errors')
    axes[1, 0].legend()
    axes[1, 0].grid(True, alpha=0.3)
    
    # Alpha errors
    axes[1, 1].plot(time_steps, filt_alpha_diff, 'b-', linewidth=1.5, label='Filtered Error', alpha=0.7)
    axes[1, 1].plot(time_steps, pred_alpha_diff, 'r--', linewidth=1.5, label='Prediction Error', alpha=0.7)
    axes[1, 1].axhline(y=0, color='k', linestyle='-', linewidth=0.5, alpha=0.3)
    axes[1, 1].set_ylabel('Error (s/s)')
    axes[1, 1].set_title('Clock Skew Errors')
    axes[1, 1].legend()
    axes[1, 1].grid(True, alpha=0.3)
    
    # Trend estimation
    axes[2, 0].plot(time_steps, filt_trend, 'b-', linewidth=1.5, label='Filtered Trend', alpha=0.7)
    axes[2, 0].plot(time_steps, pred_trend, 'r--', linewidth=1.5, label='Predicted Trend', alpha=0.7)
    axes[2, 0].axhline(y=true_trend, color='k', linestyle='-', linewidth=1.5, label=f'True Trend ({true_trend:.2e})', alpha=0.7)
    axes[2, 0].set_xlabel(f'Time ({timeScale})')
    axes[2, 0].set_ylabel('Trend (s/s)')
    axes[2, 0].set_title('Trend Estimation')
    axes[2, 0].legend()
    axes[2, 0].grid(True, alpha=0.3)
    
    # Trend error
    filt_trend_error = filt_trend - true_trend
    pred_trend_error = pred_trend - true_trend
    axes[2, 1].plot(time_steps, filt_trend_error, 'b-', linewidth=1.5, label='Filtered Trend Error', alpha=0.7)
    axes[2, 1].plot(time_steps, pred_trend_error, 'r--', linewidth=1.5, label='Predicted Trend Error', alpha=0.7)
    axes[2, 1].axhline(y=0, color='k', linestyle='-', linewidth=0.5, alpha=0.3)
    axes[2, 1].set_xlabel(f'Time ({timeScale})')
    axes[2, 1].set_ylabel('Trend Error (s/s)')
    axes[2, 1].set_title('Trend Estimation Error')
    axes[2, 1].legend()
    axes[2, 1].grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.show()


def compare_AR1_sparse_kalman(AR1_data, filtered_data, prediction_data, measurement_interval=120):
    """
    Compare AR1 raw data with sparse-measurement Kalman filtered data.
    
    Args:
        AR1_data: Raw AR1 model data (true trajectory)
        filtered_data: Kalman filtered estimates at all time steps
        prediction_data: Pure prediction estimates (before updates)
        measurement_interval: Samples between measurements
    """
    AR1_data = np.array(AR1_data)
    filtered_data = np.array(filtered_data)
    prediction_data = np.array(prediction_data)
    
    raw_theta = AR1_data[:, 0]
    raw_alpha = AR1_data[:, 1]
    
    filt_theta = filtered_data[:, 0]
    filt_alpha = filtered_data[:, 1]
    
    pred_theta = prediction_data[:, 0]
    pred_alpha = prediction_data[:, 1]
    
    # Calculate differences
    filt_theta_diff = raw_theta - filt_theta
    pred_theta_diff = raw_theta - pred_theta
    filt_alpha_diff = raw_alpha - filt_alpha
    pred_alpha_diff = raw_alpha - pred_alpha
    
    # Calculate statistics
    print("\n=== Sparse Measurement Kalman Filter Comparison ===")
    print(f"Measurement Interval: {measurement_interval} samples")
    print("\nClock Drift (Theta):")
    print(f"  Raw - Std: {np.std(raw_theta):.6e}")
    print(f"  Filtered - Std: {np.std(filt_theta):.6e}")
    print(f"  Prediction Only - Std: {np.std(pred_theta):.6e}")
    print(f"  Filtered Error - Std: {np.std(filt_theta_diff):.6e}")
    print(f"  Prediction Error - Std: {np.std(pred_theta_diff):.6e}")
    
    print("\nClock Skew (Alpha):")
    print(f"  Raw - Std: {np.std(raw_alpha):.6e}")
    print(f"  Filtered - Std: {np.std(filt_alpha):.6e}")
    print(f"  Prediction Only - Std: {np.std(pred_alpha):.6e}")
    print(f"  Filtered Error - Std: {np.std(filt_alpha_diff):.6e}")
    print(f"  Prediction Error - Std: {np.std(pred_alpha_diff):.6e}")
    
    # Create comparison plot
    fig, axes = plt.subplots(2, 2, figsize=(18, 10))
    time_steps = np.arange(len(AR1_data))
    
    # Measurement time steps
    meas_times = np.arange(measurement_interval - 1, len(AR1_data), measurement_interval)
    
    # Theta comparison
    axes[0, 0].plot(time_steps, raw_theta, 'k-', linewidth=1, label='True', alpha=0.6)
    axes[0, 0].plot(time_steps, filt_theta, 'b-', linewidth=1.5, label='Filtered (with updates)', alpha=0.7)
    axes[0, 0].plot(time_steps, pred_theta, 'r--', linewidth=1.5, label='Prediction only', alpha=0.7)
    axes[0, 0].scatter(meas_times, raw_theta[meas_times], color='green', s=20, label='Measurements', zorder=5)
    axes[0, 0].set_ylabel('Clock Drift (seconds)')
    axes[0, 0].set_title('Clock Drift: True vs Filtered vs Prediction')
    axes[0, 0].legend()
    axes[0, 0].grid(True, alpha=0.3)
    
    # Alpha comparison
    axes[0, 1].plot(time_steps, raw_alpha, 'k-', linewidth=1, label='True', alpha=0.6)
    axes[0, 1].plot(time_steps, filt_alpha, 'b-', linewidth=1.5, label='Filtered (with updates)', alpha=0.7)
    axes[0, 1].plot(time_steps, pred_alpha, 'r--', linewidth=1.5, label='Prediction only', alpha=0.7)
    axes[0, 1].scatter(meas_times, raw_alpha[meas_times], color='green', s=20, label='Measurements', zorder=5)
    axes[0, 1].set_ylabel('Clock Skew (s/s)')
    axes[0, 1].set_title('Clock Skew: True vs Filtered vs Prediction')
    axes[0, 1].legend()
    axes[0, 1].grid(True, alpha=0.3)
    
    # Theta errors
    axes[1, 0].plot(time_steps, filt_theta_diff, 'b-', linewidth=1.5, label='Filtered Error', alpha=0.7)
    axes[1, 0].plot(time_steps, pred_theta_diff, 'r--', linewidth=1.5, label='Prediction Error', alpha=0.7)
    axes[1, 0].axhline(y=0, color='k', linestyle='-', linewidth=0.5, alpha=0.3)
    axes[1, 0].set_xlabel(f'Time ({timeScale})')
    axes[1, 0].set_ylabel('Error (seconds)')
    axes[1, 0].set_title('Clock Drift Errors')
    axes[1, 0].legend()
    axes[1, 0].grid(True, alpha=0.3)
    
    # Alpha errors
    axes[1, 1].plot(time_steps, filt_alpha_diff, 'b-', linewidth=1.5, label='Filtered Error', alpha=0.7)
    axes[1, 1].plot(time_steps, pred_alpha_diff, 'r--', linewidth=1.5, label='Prediction Error', alpha=0.7)
    axes[1, 1].axhline(y=0, color='k', linestyle='-', linewidth=0.5, alpha=0.3)
    axes[1, 1].set_xlabel(f'Time ({timeScale})')
    axes[1, 1].set_ylabel('Error (s/s)')
    axes[1, 1].set_title('Clock Skew Errors')
    axes[1, 1].legend()
    axes[1, 1].grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.show()


def plot_AR1_vs_AR5(AR1_data, AR5_data):
    """
    Plot AR1 and AR5 model data on the same plot for direct comparison.
    
    Args:
        AR1_data: AR1 model data (list or array of [theta, alpha] pairs)
        AR5_data: AR5 model data (list or array of [theta, alpha] pairs)
    """
    # Convert to numpy arrays if needed
    AR1_data = np.array(AR1_data)
    AR5_data = np.array(AR5_data)
    
    # Extract theta and alpha values
    AR1_theta = AR1_data[:, 0]
    AR1_alpha = AR1_data[:, 1]
    AR5_theta = AR5_data[:, 0]
    AR5_alpha = AR5_data[:, 1]
    
    # Create time steps
    AR1_time = np.arange(len(AR1_data))
    AR5_time = np.arange(len(AR5_data))
    
    # Create figure with two subplots
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))
    
    # Plot theta (clock drift) comparison
    ax1.plot(AR5_time, AR5_theta, 'b-', linewidth=2, label='AR5 Clock Drift', alpha=0.7)
    ax1.plot(AR1_time, AR1_theta, 'r--', linewidth=2, label='AR1 Clock Drift', alpha=0.7)
    ax1.set_xlabel(f'Time ({timeScale})')
    ax1.set_ylabel('Clock Drift (seconds)')
    ax1.set_title('Clock Drift Comparison: AR5 vs AR1')
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc='best')
    
    # Plot alpha (clock skew) comparison
    ax2.plot(AR5_time, AR5_alpha, 'b-', linewidth=2, label='AR5 Clock Skew', alpha=0.7)
    ax2.plot(AR1_time, AR1_alpha, 'r--', linewidth=2, label='AR1 Clock Skew', alpha=0.7)
    ax2.set_xlabel(f'Time ({timeScale})')
    ax2.set_ylabel('Clock Skew (s/s)')
    ax2.set_title('Clock Skew Comparison: AR5 vs AR1')
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc='best')
    
    plt.tight_layout()
    plt.show()
    
    # Print comparison statistics
    print(f"\n=== Clock Drift (Theta) Comparison ===")
    print(f"AR5: Min={np.min(AR5_theta):.6e}, Max={np.max(AR5_theta):.6e}, Mean={np.mean(AR5_theta):.6e}, Std={np.std(AR5_theta):.6e}")
    print(f"AR1: Min={np.min(AR1_theta):.6e}, Max={np.max(AR1_theta):.6e}, Mean={np.mean(AR1_theta):.6e}, Std={np.std(AR1_theta):.6e}")
    
    print(f"\n=== Clock Skew (Alpha) Comparison ===")
    print(f"AR5: Min={np.min(AR5_alpha):.6e}, Max={np.max(AR5_alpha):.6e}, Mean={np.mean(AR5_alpha):.6e}, Std={np.std(AR5_alpha):.6e}")
    print(f"AR1: Min={np.min(AR1_alpha):.6e}, Max={np.max(AR1_alpha):.6e}, Mean={np.mean(AR1_alpha):.6e}, Std={np.std(AR1_alpha):.6e}")


def analysis(AR1data, AR5data):
    timeLagMax = 50

    AR5ACF = np.correlate(AR5data[:, 1], AR5data[:, 1], mode = "full")
    AR5ACF = AR5ACF[AR5ACF.size//2:]
    AR5ACF = AR5ACF/AR5ACF[0] #Normalize the ACF
    ACF5_truncated = AR5ACF[:timeLagMax]

    AR1ACF = np.correlate(AR1data[:, 1], AR1data[:, 1], mode = "full")
    AR1ACF = AR1ACF[AR1ACF.size//2:]
    AR1ACF = AR1ACF/AR1ACF[0] #Normalize the ACF
    ACF1_truncated = AR1ACF[:timeLagMax]

    # Compute PSDs via FFT of truncated ACFs
    AR5PSD = np.abs(np.fft.fft(ACF5_truncated))**2
    AR1PSD = np.abs(np.fft.fft(ACF1_truncated))**2

    # Plot ACFs and PSDs on the same figure
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    
    lags = np.arange(timeLagMax)
    ax1.plot(lags, AR5ACF[:timeLagMax], 'b-', linewidth=2, label='AR5 ACF', alpha=0.7)
    ax1.plot(lags, AR1ACF[:timeLagMax], 'r-', linewidth=2, label='AR1 ACF', alpha=0.7)
    
    ax1.set_xlabel('Lag')
    ax1.set_ylabel('Autocorrelation')
    ax1.set_title('Autocorrelation Functions normalized: AR5 vs AR1')
    ax1.legend()
    ax1.grid(True, alpha=0.3, which='both')
    
    # Plot PSDs
    freqs = np.fft.fftfreq(timeLagMax)
    ax2.plot(freqs, AR5PSD, 'b-', linewidth=2, label='AR5 PSD', alpha=0.7)
    ax2.plot(freqs, AR1PSD, 'r-', linewidth=2, label='AR1 PSD', alpha=0.7)
    
    ax2.set_xlabel('Frequency')
    ax2.set_ylabel('Power Spectral Density')
    ax2.set_title('Power Spectral Densities: AR5 vs AR1')
    ax2.legend()
    ax2.grid(True, alpha=0.3, which='both')
    
    plt.tight_layout()
    plt.show()

def main ():
    # AR1 model with trend (40 microseconds per second drift)
    trend_rate = 4e-5  # seconds per second
    AR5data = np.array(ARModelSimple())
    AR1data = np.array(AR1Model(trend_rate=trend_rate))  
    
    print(f"AR1 Model with trend rate: {trend_rate} s/s ({trend_rate*1e6:.1f} µs/s)")

    # Apply 3-state Kalman filter to AR1 data with sparse measurements
    # t0=60 means 1 minute wake-up
    # measurement_interval=120 means updates every 120*60 = 7200 seconds = 2 hours
    measurement_interval = 120
    AR1_filtered_3state, AR1_prediction_3state = apply_kalman_filter_to_AR1_sparse_with_trend(
        AR1data, 
        process_noise_scale=0.5, 
        measurement_noise_scale=1e-30,  # Nearly zero for perfect measurements
        measurement_interval=measurement_interval
    )

    # Plot 10 realizations on the same plot
    # plot_multiple_realizations(num_realizations=10)

    #Temperature based drift
    # data = tempModel(start = 1) #Write month number
    
    # plotData(AR5data)
    # plotData(AR1data)
    # plot_psd()
    
    # Uncomment one of the following to see different comparisons:
    # plot_AR1_vs_AR5(AR1_data=AR1data, AR5_data=AR5data)
    # plot_AR1_with_kalman(AR1data, AR1_filtered)
    # compare_AR1_and_kalman(AR1data, AR1_filtered)
    # compare_AR1_sparse_kalman(AR1data, AR1_filtered, AR1_prediction, measurement_interval)
    compare_AR1_sparse_kalman_3state(AR1data, AR1_filtered_3state, AR1_prediction_3state, 
                                      measurement_interval, true_trend=trend_rate)
    # analysis(AR1data, AR5data)





if __name__=="__main__":
    main()