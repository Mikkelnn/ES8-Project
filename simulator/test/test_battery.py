from node.battery.battery import Battery


class TestBatteryLinear:
	"""Test battery discharge and charge linearity."""

	def test_constant_discharge_linear(self):
		"""Constant consumption → linear discharge."""
		battery = Battery(capacity_joule=100, recharge_rate_joule_per_second=0, second_to_global_tick=1)
		consumption_per_tick = 10

		charges = []
		for tick in range(1, 11):
			_, _ = battery.tick(tick, consumption_per_tick)
			charges.append(battery.current_charge)

		# Expected: 100 - (10 * 1), 100 - (10 * 2), ..., 100 - (10 * 10)
		expected = [100 - (consumption_per_tick * i) for i in range(1, 11)]
		assert charges == expected, f"Got {charges}, expected {expected}"

	def test_constant_recharge_linear(self):
		"""Constant recharge with no consumption → stays at capacity (already full)."""
		battery = Battery(capacity_joule=100, recharge_rate_joule_per_second=10, second_to_global_tick=1)
		# Battery starts at capacity (100), recharging with no consumption keeps it at capacity

		charges = []
		for tick in range(1, 11):
			_, _ = battery.tick(tick, current_consumption_joule=0)
			charges.append(battery.current_charge)

		# Expected: all 100 (battery starts full, stays full)
		expected = [100] * 10
		assert charges == expected, f"Got {charges}, expected {expected}"

	def test_net_zero_holds_charge(self):
		"""Recharge rate == consumption → constant charge."""
		recharge = 5
		battery = Battery(capacity_joule=100, recharge_rate_joule_per_second=recharge, second_to_global_tick=1)

		charges = []
		for tick in range(1, 11):
			_, _ = battery.tick(tick, current_consumption_joule=recharge)
			charges.append(battery.current_charge)

		expected = [100] * 10
		assert charges == expected, f"Got {charges}, expected {expected}"

	def test_discharge_to_zero_clamped(self):
		"""Discharge below 0 → clamped to 0."""
		battery = Battery(capacity_joule=10, recharge_rate_joule_per_second=0, second_to_global_tick=1)

		charges = []
		for tick in range(1, 15):
			_, _ = battery.tick(tick, current_consumption_joule=5)
			charges.append(battery.current_charge)

		# 10-5=5, 5-5=0, 0-5 clamped to 0, etc.
		expected = [5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
		assert charges == expected, f"Got {charges}, expected {expected}"

	def test_recharge_to_capacity_clamped(self):
		"""Recharge above capacity → clamped to capacity."""
		battery = Battery(capacity_joule=50, recharge_rate_joule_per_second=30, second_to_global_tick=1)
		battery.current_charge = 40

		charges = []
		for tick in range(1, 6):
			_, _ = battery.tick(tick, current_consumption_joule=0)
			charges.append(battery.current_charge)

		# 40+30=70 clamped to 50, 50+30=80 clamped to 50, etc.
		expected = [50, 50, 50, 50, 50]
		assert charges == expected, f"Got {charges}, expected {expected}"


class TestBatteryDeathPrediction:
	"""Test death tick prediction."""

	def test_death_prediction_exact(self):
		"""Predict death when consuming more than recharging."""
		battery = Battery(capacity_joule=100, recharge_rate_joule_per_second=0, second_to_global_tick=1)
		consumption = 10

		_, next_tick = battery.tick(1, consumption)
		# After tick 1: charge = 90, net_change = -10
		# Death at: 1 + ceil(90 / 10) = 1 + 9 = 10
		assert next_tick == 10, f"Expected death at tick 10, got {next_tick}"

	def test_death_prediction_small_consumption(self):
		"""Predict death with small consumption rate."""
		battery = Battery(capacity_joule=50, recharge_rate_joule_per_second=0, second_to_global_tick=1)
		consumption = 1

		_, next_tick = battery.tick(1, consumption)
		# After tick 1: charge = 49, net_change = -1
		# Death at: 1 + ceil(49 / 1) = 50
		assert next_tick == 50, f"Expected death at tick 50, got {next_tick}"

	def test_no_death_prediction_when_recharging(self):
		"""No death predicted when recharging."""
		battery = Battery(capacity_joule=100, recharge_rate_joule_per_second=10, second_to_global_tick=1)

		_, next_tick = battery.tick(1, current_consumption_joule=5)
		# net_change = 10 - 5 = 5 (positive), no death
		assert next_tick is None, f"Expected no death prediction, got {next_tick}"

	def test_no_death_prediction_when_net_zero(self):
		"""No death when consumption == recharge."""
		battery = Battery(capacity_joule=100, recharge_rate_joule_per_second=5, second_to_global_tick=1)

		_, next_tick = battery.tick(1, current_consumption_joule=5)
		assert next_tick is None, f"Expected no death prediction at net zero, got {next_tick}"

	def test_death_reported_when_dead(self):
		"""Death predicted immediately when already dead."""
		battery = Battery(capacity_joule=100, recharge_rate_joule_per_second=0, second_to_global_tick=1)
		battery.current_charge = 0

		_, next_tick = battery.tick(1, current_consumption_joule=1)
		assert next_tick == 2, f"Expected death reported at next tick, got {next_tick}"


class TestBatteryWarp:
	"""Test warp (skipped ticks) handling."""

	def test_warp_applies_prev_consumption(self):
		"""Skipped ticks apply previous consumption rate."""
		battery = Battery(capacity_joule=1000, recharge_rate_joule_per_second=0, second_to_global_tick=1)

		# Tick 1: consume 10, charge = 990
		battery.tick(1, current_consumption_joule=10)
		assert battery.current_charge == 990

		# Tick 5 (skip 2,3,4): apply tick 1 consumption (10) to warped ticks (3 skipped)
		# warped_ticks = 5 - 1 - 1 = 3
		# warp consumption: 10 * 3 = 30
		# current tick consumption: 10
		# total: 990 - 30 - 10 = 950
		battery.tick(5, current_consumption_joule=10)
		assert battery.current_charge == 950

	def test_warp_zero_skipped_ticks(self):
		"""No warp when ticking sequentially."""
		battery = Battery(capacity_joule=100, recharge_rate_joule_per_second=0, second_to_global_tick=1)

		battery.tick(1, current_consumption_joule=10)
		battery.tick(2, current_consumption_joule=10)
		battery.tick(3, current_consumption_joule=10)

		# 100 - 10 - 10 - 10 = 70
		assert battery.current_charge == 70

	def test_warp_with_recharge(self):
		"""Warp applies previous net change (recharge - consumption)."""
		battery = Battery(capacity_joule=1000, recharge_rate_joule_per_second=50, second_to_global_tick=1)

		# Tick 1: recharge 50, consume 20, net +30, charge = 1000 (clamped)
		battery.tick(1, current_consumption_joule=20)

		# Tick 10 (skip 2-9): apply net +30 for 8 warped ticks
		# warp gain: 30 * 8 = 240
		# current tick gain: 50 - 30 = 20
		# total: 1000 + 240 + 20 = 1260, clamped to 1000
		battery.tick(10, current_consumption_joule=30)
		assert battery.current_charge == 1000  # Clamped


class TestBatteryEdgeCases:
	"""Test edge cases."""

	def test_zero_recharge_rate(self):
		"""Battery with no recharge source."""
		battery = Battery(capacity_joule=10, recharge_rate_joule_per_second=0, second_to_global_tick=1)
		assert battery.current_charge == 10
		battery.tick(1, current_consumption_joule=0)
		assert battery.current_charge == 10

	def test_is_dead_at_zero(self):
		"""is_dead() returns True at charge <= 0."""
		battery = Battery(capacity_joule=10, recharge_rate_joule_per_second=0, second_to_global_tick=1)
		battery.tick(1, current_consumption_joule=15)
		assert battery.is_dead()

	def test_is_not_dead_above_zero(self):
		"""is_dead() returns False at charge > 0."""
		battery = Battery(capacity_joule=10, recharge_rate_joule_per_second=0, second_to_global_tick=1)
		battery.tick(1, current_consumption_joule=5)
		assert not battery.is_dead()

	def test_fractional_consumption(self):
		"""Handle fractional joule consumption."""
		battery = Battery(capacity_joule=10, recharge_rate_joule_per_second=0, second_to_global_tick=0.001)
		recharge = 5 * 0.001  # 5 J/s * 0.001 s = 0.005 J/tick

		battery = Battery(capacity_joule=10, recharge_rate_joule_per_second=5, second_to_global_tick=0.001)
		battery.tick(1, current_consumption_joule=0.002)
		assert 9.998 < battery.current_charge < 10.01  # Allow floating point variance

	def test_reset_clears_state(self):
		"""reset() does not reset charge level, only internal state."""
		battery = Battery(capacity_joule=100, recharge_rate_joule_per_second=10, second_to_global_tick=1)
		battery.tick(1, current_consumption_joule=5)
		charge_before_reset = battery.current_charge
		battery.reset(1)
		# reset() doesn't change charge, just clears internal tick tracking
		assert battery.current_charge == charge_before_reset


class TestBatteryScenarios:
	"""Integration scenarios."""

	def test_discharge_then_recharge_cycle(self):
		"""Battery discharges, then switches to recharging."""
		battery = Battery(capacity_joule=100, recharge_rate_joule_per_second=20, second_to_global_tick=1)

		# Ticks 1-5: discharge (consume 50, recharge 20, net -30/tick)
		for tick in range(1, 6):
			battery.tick(tick, current_consumption_joule=50)
		# Charge: 100 - (30*5) = -50, clamped to 0
		assert battery.current_charge == 0
		assert battery.is_dead()

		# Ticks 6-10: try to recharge (consume 0, recharge 20)
		for tick in range(6, 11):
			battery.tick(tick, current_consumption_joule=0)
		# Still dead (was dead, stays dead until reset)
		assert battery.current_charge == 100  # Recharges to capacity
		assert not battery.is_dead()

	def test_real_world_lorawan_node(self):
		"""Realistic LoRaWAN node: high consumption drains despite recharge."""
		# 7.9 J capacity, 5.4 J/s recharge (from simulator)
		battery = Battery(capacity_joule=7.9, recharge_rate_joule_per_second=5.4, second_to_global_tick=0.001)

		# Simulate: high consumption (e.g., TX) for 100 ticks that exceeds recharge
		high_consumption = 0.396  # TX power from LoRaD2D
		for tick in range(1, 101):
			battery.tick(tick, current_consumption_joule=high_consumption)

		# Should have discharged (consumption > recharge)
		assert battery.current_charge < 7.9
