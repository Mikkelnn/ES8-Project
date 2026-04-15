from math import log10


frequency_hz = 868_100_000
tx_eirp_dbm = 16
rx_antenna_gain_dbi = 0
rx_cable_loss_db = 0
fade_margin_db = 15
path_loss_exponent = 2.7
reference_distance_m = 1
fspl_offset_db = 147.55

spreading_factor = 7
bandwidth_hz = 125_000
soil_conditions_loss_db = {
    "dry dirt": 0.08,
    "7% wet dirt": 6.68,
    "22% wet dirt": 11.02,
    "30% wet dirt": 32.06,
}

sx1276_sensitivity_by_sf_dbm = {
    7: -123.0,
    8: -126.0,
    9: -129.0,
    10: -132.0,
    11: -134.5,
    12: -137.0,
}


def receiver_sensitivity_dbm() -> float:
    if bandwidth_hz != 125_000:
        raise ValueError("SX1276 sensitivity table is only valid for 125 kHz bandwidth")
    return sx1276_sensitivity_by_sf_dbm[spreading_factor]


def max_allowable_path_loss_db() -> float:
    return (
        tx_eirp_dbm
        + rx_antenna_gain_dbi
        - rx_cable_loss_db
        - receiver_sensitivity_dbm()
        - fade_margin_db
    )


def max_allowable_path_loss_db_with_ground_loss(underground_loss_db: float) -> float:
    return max_allowable_path_loss_db() - underground_loss_db


def free_space_path_loss_db(distance_m: float) -> float:
    return 20 * log10(distance_m) + 20 * log10(frequency_hz) - fspl_offset_db


def max_free_space_radius_m() -> float:
    path_loss_db = max_allowable_path_loss_db()
    exponent = (path_loss_db - 20 * log10(frequency_hz) + fspl_offset_db) / 20
    return 10**exponent


def max_log_distance_radius_m(underground_loss_db: float) -> float:
    path_loss_db = max_allowable_path_loss_db_with_ground_loss(underground_loss_db)
    reference_loss_db = free_space_path_loss_db(reference_distance_m)
    exponent = (path_loss_db - reference_loss_db) / (10 * path_loss_exponent)
    return reference_distance_m * (10**exponent)


def main():
    print("EU868 LoRa with SX1276")
    print(f"  Frequency: {frequency_hz / 1_000_000:.1f} MHz")
    print(f"  Tx EIRP: {tx_eirp_dbm:.1f} dBm")
    print(f"  Rx antenna gain: {rx_antenna_gain_dbi:.1f} dBi")
    print(f"  SF: {spreading_factor}")
    print(f"  Bandwidth: {bandwidth_hz / 1000:.0f} kHz")
    print(f"  SX1276 sensitivity: {receiver_sensitivity_dbm():.2f} dBm")
    print(f"  Fade margin: {fade_margin_db:.2f} dB")
    print(f"  Path loss exponent: {path_loss_exponent}")
    print()
    free_space_radius_m = max_free_space_radius_m()
    max_path_loss_db_free_space = max_allowable_path_loss_db()
    print("Free space (no ground effects):")
    print(f"  Max allowable path loss: {max_path_loss_db_free_space:.2f} dB")
    print(f"  Max radius: {free_space_radius_m / 1000:.2f} km")
    print()
    print("Coverage with ground attenuation (log-distance model):")
    print("-" * 85)
    print(f"{'Soil Condition':<20} {'Loss (dB)':<12} {'Max Path Loss (dB)':<20} {'Max Radius (km)':<15}")
    print("-" * 85)
    for soil_name, loss_db in soil_conditions_loss_db.items():
        max_path_loss_db = max_allowable_path_loss_db_with_ground_loss(loss_db)
        log_distance_radius_m = max_log_distance_radius_m(loss_db)
        print(f"{soil_name:<20} {loss_db:<12.2f} {max_path_loss_db:<20.2f} {log_distance_radius_m / 1000:<15.2f}")
    print("-" * 85)


if __name__ == "__main__":
    main()