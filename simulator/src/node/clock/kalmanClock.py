import numpy as np

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
    
    def __init__(self, process_noise_var, measurement_noise_var, c1, t0_val=1):
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
    
    def predict(self, k):
        """Prediction step of 3-state Kalman filter."""
        q = self.process_noise_var

        # Closed-form F^k
        if k > 1000:
            c1k = 0.0
            c12k = 0.0
            s = self.c1 / (1.0 - self.c1)
        else:
            c1k = self.c1**k
            c12k = (self.c1 * self.c1)**k
            s = self.c1 * (1.0 - c1k) / (1.0 - self.c1)

        Fk = np.array([
            [1.0, s, float(k)],
            [0.0, c1k, 0.0],
            [0.0, 0.0, 1.0],
        ])

        # State prediction
        self.x = Fk @ self.x

        # Process noise accumulation
        A = 1.0 / (1.0 - self.c1)

        s22 = (1.0 - c12k) / (1.0 - self.c1 * self.c1)

        s12 = (
            A * (1.0 - c1k) / (1.0 - self.c1)
            - self.c1 * (1.0 - c12k)
            / ((1.0 - self.c1) * (1.0 - self.c1 * self.c1))
        )

        s11 = (
            k * A * A
            - 2.0 * A * self.c1 * (1.0 - c1k)
            / ((1.0 - self.c1) ** 2)
            + self.c1 * self.c1 * (1.0 - c12k)
            / (((1.0 - self.c1) ** 2) * (1.0 - self.c1 * self.c1))
        )

        Sk = q * np.array([
            [s11, s12, 0.0],
            [s12, s22, 0.0],
            [0.0, 0.0, 0.0],
        ])

        # Covariance prediction
        self.P = Fk @ self.P @ Fk.T + Sk

        return self.x            
    
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

        return self.x
