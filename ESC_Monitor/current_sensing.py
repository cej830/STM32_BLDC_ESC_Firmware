"""Convert the selected low-side shunt sample; no PWM validity is inferred."""
import config


# Matches algorithm_BLDC_Control.c sixstep(): (PWM source, low-side sink).
STEP_PHASES = {
    1: ("A", "B"), 2: ("A", "C"), 3: ("B", "C"),
    4: ("B", "A"), 5: ("C", "A"), 6: ("C", "B"),
}


def measure_current(pkt):
    result = {
        "drive_phase": "", "low_side_phase": "", "current_raw": None,
        "shunt_amp_voltage_v": None, "current_a": None,
        "current_status": "INVALID_STEP",
    }
    phases = STEP_PHASES.get(pkt["step"])
    if phases is None:
        return result
    source, sink = phases
    raw = pkt[f"shunt_{sink.lower()}"]
    result.update(drive_phase=source, low_side_phase=sink, current_raw=raw)
    if not 0 <= raw <= config.CURRENT_ADC_MAX:
        result["current_status"] = "ADC_OUT_OF_RANGE"
        return result
    volts_per_code = config.CURRENT_ADC_VREF_V / config.CURRENT_ADC_MAX
    result["shunt_amp_voltage_v"] = raw * volts_per_code
    result["current_a"] = (
        (raw - config.SHUNT_ZERO_ADC[sink]) * volts_per_code
        / (config.SHUNT_RESISTANCE_OHM * config.SHUNT_AMPLIFIER_GAIN)
    )
    result["current_status"] = (
        "ADC_HIGH_RAIL" if raw == config.CURRENT_ADC_MAX else
        "ADC_LOW_RAIL" if raw == 0 else "ESTIMATE"
    )
    return result
