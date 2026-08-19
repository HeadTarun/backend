"""Comprehensive evaluation smoke test — covers diverse industrial product categories."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from product_agent.schemas import (
    ProductInput,
    ProductIntelligence,
    ProductSpec,
    SourceEvidence,
    Confidence,
    EvaluationRequest,
)
from product_agent.evaluation import evaluate_product_output


# ---------------------------------------------------------------------------
# Test product catalog — one entry per major industrial category
# ---------------------------------------------------------------------------
TEST_PRODUCTS: list[dict] = [
    # 1. Proximity Sensor
    {
        "input": ProductInput(
            manufacturer_part_number="XS618B1PAL2",
            brand="Schneider Electric",
            short_description="Inductive proximity sensor 18mm 24VDC PNP NO",
        ),
        "output": ProductIntelligence(
            manufacturer_part_number="XS618B1PAL2",
            brand="Schneider Electric",
            title="Schneider Electric XS618B1PAL2 Inductive Proximity Sensor",
            category="Sensors & Encoders",
            commerce_description=(
                "Schneider Electric XS618B1PAL2 inductive proximity sensor with 18 mm "
                "cylindrical housing, 24 VDC supply, PNP normally-open output, and "
                "flush-mount design for factory automation detection tasks."
            ),
            key_features=["18 mm barrel housing", "24 VDC supply", "PNP NO output", "IP67 rated"],
            specifications=[
                ProductSpec(name="Supply Voltage", value="24", unit="VDC", source="extracted_spec"),
                ProductSpec(name="Sensing Distance", value="8", unit="mm", source="extracted_spec"),
                ProductSpec(name="Housing Diameter", value="18", unit="mm", source="extracted_spec"),
            ],
            applications=["Conveyor systems", "Packaging machines", "Assembly lines"],
            normalized_attributes={"supply_voltage": "24 VDC", "sensing_distance": "8 mm"},
            source_evidence=[SourceEvidence(source_type="input", locator="short_description", excerpt="Inductive proximity sensor 18mm 24VDC PNP NO")],
            confidence=Confidence.medium,
        ),
    },
    # 2. Three-Phase AC Motor
    {
        "input": ProductInput(
            manufacturer_part_number="1LA7096-4AA10",
            brand="Siemens",
            short_description="3-phase asynchronous motor 1.5 kW 230/400V 1420 RPM",
        ),
        "output": ProductIntelligence(
            manufacturer_part_number="1LA7096-4AA10",
            brand="Siemens",
            title="Siemens 1LA7096-4AA10 Three-Phase Asynchronous Motor",
            category="Electric Motors & Drives",
            commerce_description=(
                "Siemens SIMOTICS GP 1LA7096-4AA10 three-phase asynchronous motor rated "
                "at 1.5 kW, 230/400 V, 1420 RPM with IE2 efficiency class and IP55 "
                "enclosure for general-purpose industrial drive applications."
            ),
            key_features=["1.5 kW output", "IE2 efficiency", "IP55 enclosure", "IEC frame size 90"],
            specifications=[
                ProductSpec(name="Rated Power", value="1.5", unit="kW", source="extracted_spec"),
                ProductSpec(name="Supply Voltage", value="230/400", unit="V", source="extracted_spec"),
                ProductSpec(name="Speed", value="1420", unit="RPM", source="extracted_spec"),
                ProductSpec(name="Frequency", value="50", unit="Hz", source="inferred"),
            ],
            applications=["Pump drives", "Fan systems", "Compressor units", "General machinery"],
            normalized_attributes={"rated_power": "1.5 kW", "supply_voltage": "230/400 V", "speed": "1420 RPM"},
            source_evidence=[SourceEvidence(source_type="input", locator="short_description", excerpt="3-phase asynchronous motor 1.5 kW 230/400V 1420 RPM")],
            confidence=Confidence.medium,
        ),
    },
    # 3. Variable Frequency Drive (VFD)
    {
        "input": ProductInput(
            manufacturer_part_number="ATV320U22N4B",
            brand="Schneider Electric",
            short_description="Variable speed drive 2.2kW 380-500V 3-phase",
        ),
        "output": ProductIntelligence(
            manufacturer_part_number="ATV320U22N4B",
            brand="Schneider Electric",
            title="Schneider Electric Altivar 320 Variable Speed Drive 2.2 kW",
            category="Drives & Motor Controls",
            commerce_description=(
                "Schneider Electric Altivar ATV320U22N4B compact variable speed drive "
                "for 2.2 kW three-phase motors, 380-500 V input, built-in EMC filter, "
                "SIL2 safety input, and embedded Modbus communication."
            ),
            key_features=["2.2 kW rating", "380-500 V 3-phase input", "Built-in EMC filter", "Modbus RTU"],
            specifications=[
                ProductSpec(name="Motor Power", value="2.2", unit="kW", source="extracted_spec"),
                ProductSpec(name="Input Voltage", value="380-500", unit="V", source="extracted_spec"),
                ProductSpec(name="Output Frequency", value="0.5-599", unit="Hz", source="inferred"),
            ],
            applications=["HVAC fans", "Pump speed control", "Conveyor drives", "Mixing equipment"],
            normalized_attributes={"motor_power": "2.2 kW", "input_voltage": "380-500 V"},
            source_evidence=[SourceEvidence(source_type="input", locator="short_description", excerpt="Variable speed drive 2.2kW 380-500V 3-phase")],
            confidence=Confidence.medium,
        ),
    },
    # 4. Programmable Logic Controller (PLC)
    {
        "input": ProductInput(
            manufacturer_part_number="6ES7214-1AG40-0XB0",
            brand="Siemens",
            short_description="SIMATIC S7-1200 CPU 1214C DC/DC/DC 14DI 10DO 2AI",
        ),
        "output": ProductIntelligence(
            manufacturer_part_number="6ES7214-1AG40-0XB0",
            brand="Siemens",
            title="Siemens SIMATIC S7-1200 CPU 1214C Compact PLC",
            category="Programmable Logic Controllers",
            commerce_description=(
                "Siemens SIMATIC S7-1200 CPU 1214C compact PLC with DC/DC/DC power "
                "supply, 14 digital inputs, 10 digital outputs, 2 analog inputs, "
                "100 KB program memory, and PROFINET interface for small to mid-range "
                "automation projects."
            ),
            key_features=["14 DI / 10 DO / 2 AI", "DC/DC/DC supply", "PROFINET onboard", "100 KB work memory"],
            specifications=[
                ProductSpec(name="Digital Inputs", value="14", unit=None, source="extracted_spec"),
                ProductSpec(name="Digital Outputs", value="10", unit=None, source="extracted_spec"),
                ProductSpec(name="Analog Inputs", value="2", unit=None, source="extracted_spec"),
                ProductSpec(name="Supply Voltage", value="24", unit="VDC", source="inferred"),
            ],
            applications=["Machine control", "Building automation", "Process control", "Material handling"],
            normalized_attributes={"digital_inputs": "14", "digital_outputs": "10", "analog_inputs": "2"},
            source_evidence=[SourceEvidence(source_type="input", locator="short_description", excerpt="SIMATIC S7-1200 CPU 1214C DC/DC/DC 14DI 10DO 2AI")],
            confidence=Confidence.high,
        ),
    },
    # 5. Industrial Pressure Transmitter
    {
        "input": ProductInput(
            manufacturer_part_number="3051TG2A2B21AB4M5",
            brand="Emerson",
            short_description="Rosemount 3051T pressure transmitter 0-250 psi 4-20mA HART",
        ),
        "output": ProductIntelligence(
            manufacturer_part_number="3051TG2A2B21AB4M5",
            brand="Emerson",
            title="Emerson Rosemount 3051T Gage Pressure Transmitter",
            category="Pressure Instruments",
            commerce_description=(
                "Emerson Rosemount 3051TG gage pressure transmitter with 0-250 psi "
                "range, 4-20 mA output with HART protocol, 316L SST process connection, "
                "and ±0.04% reference accuracy for process control and monitoring."
            ),
            key_features=["0-250 psi range", "4-20 mA + HART", "±0.04% accuracy", "316L SST wetted parts"],
            specifications=[
                ProductSpec(name="Pressure Range", value="0-250", unit="psi", source="extracted_spec"),
                ProductSpec(name="Output Signal", value="4-20", unit="mA", source="extracted_spec"),
                ProductSpec(name="Accuracy", value="±0.04", unit="%", source="inferred"),
            ],
            applications=["Oil & gas processing", "Water treatment", "Chemical plants", "Power generation"],
            normalized_attributes={"pressure_range": "0-250 psi", "output_signal": "4-20 mA"},
            source_evidence=[SourceEvidence(source_type="input", locator="short_description", excerpt="Rosemount 3051T pressure transmitter 0-250 psi 4-20mA HART")],
            confidence=Confidence.medium,
        ),
    },
    # 6. Industrial Circuit Breaker
    {
        "input": ProductInput(
            manufacturer_part_number="FAL36100",
            brand="Square D",
            short_description="Molded case circuit breaker 100A 600V 3-pole thermal-magnetic",
        ),
        "output": ProductIntelligence(
            manufacturer_part_number="FAL36100",
            brand="Square D",
            title="Square D FAL36100 Molded Case Circuit Breaker 100A",
            category="Circuit Breakers & Protection",
            commerce_description=(
                "Square D FAL36100 molded case circuit breaker rated 100 A, 600 V, "
                "3-pole, thermal-magnetic trip unit, 65 kA interrupting capacity at "
                "480 V for industrial power distribution and motor protection."
            ),
            key_features=["100 A rated current", "600 V max", "3-pole", "Thermal-magnetic trip", "65 kA AIC"],
            specifications=[
                ProductSpec(name="Current Rating", value="100", unit="A", source="extracted_spec"),
                ProductSpec(name="Voltage Rating", value="600", unit="V", source="extracted_spec"),
                ProductSpec(name="Poles", value="3", unit=None, source="extracted_spec"),
            ],
            applications=["Industrial switchboards", "Motor control centers", "Power distribution panels"],
            normalized_attributes={"current_rating": "100 A", "voltage_rating": "600 V", "poles": "3"},
            source_evidence=[SourceEvidence(source_type="input", locator="short_description", excerpt="Molded case circuit breaker 100A 600V 3-pole thermal-magnetic")],
            confidence=Confidence.medium,
        ),
    },
    # 7. Pneumatic Cylinder
    {
        "input": ProductInput(
            manufacturer_part_number="DSBC-50-200-PPVA-N3",
            brand="Festo",
            short_description="ISO cylinder 50mm bore 200mm stroke double-acting cushioned",
        ),
        "output": ProductIntelligence(
            manufacturer_part_number="DSBC-50-200-PPVA-N3",
            brand="Festo",
            title="Festo DSBC-50-200 ISO Standard Pneumatic Cylinder",
            category="Pneumatic Actuators",
            commerce_description=(
                "Festo DSBC series ISO 15552 standard pneumatic cylinder with 50 mm "
                "bore, 200 mm stroke, double-acting operation, adjustable pneumatic "
                "cushioning, and piston rod with anti-rotate feature."
            ),
            key_features=["50 mm bore", "200 mm stroke", "ISO 15552 compliant", "PPV cushioning"],
            specifications=[
                ProductSpec(name="Bore Diameter", value="50", unit="mm", source="extracted_spec"),
                ProductSpec(name="Stroke Length", value="200", unit="mm", source="extracted_spec"),
                ProductSpec(name="Max Pressure", value="12", unit="bar", source="inferred"),
            ],
            applications=["Clamping fixtures", "Press operations", "Pick-and-place", "Automated assembly"],
            normalized_attributes={"bore_diameter": "50 mm", "stroke_length": "200 mm"},
            source_evidence=[SourceEvidence(source_type="input", locator="short_description", excerpt="ISO cylinder 50mm bore 200mm stroke double-acting cushioned")],
            confidence=Confidence.medium,
        ),
    },
    # 8. Industrial Power Supply
    {
        "input": ProductInput(
            manufacturer_part_number="6EP1334-3BA10",
            brand="Siemens",
            short_description="SITOP PSU200M power supply 24V 10A input 120/230VAC",
        ),
        "output": ProductIntelligence(
            manufacturer_part_number="6EP1334-3BA10",
            brand="Siemens",
            title="Siemens SITOP PSU200M Stabilized Power Supply 24V/10A",
            category="Power Supplies",
            commerce_description=(
                "Siemens SITOP PSU200M regulated DIN-rail power supply providing 24 VDC "
                "at 10 A (240 W) with wide-range 120/230 VAC input, high efficiency, "
                "and integrated diagnostics for industrial automation cabinets."
            ),
            key_features=["24 VDC / 10 A output", "120/230 VAC input", "DIN-rail mount", "93% efficiency"],
            specifications=[
                ProductSpec(name="Output Voltage", value="24", unit="VDC", source="extracted_spec"),
                ProductSpec(name="Output Current", value="10", unit="A", source="extracted_spec"),
                ProductSpec(name="Input Voltage", value="120/230", unit="VAC", source="extracted_spec"),
                ProductSpec(name="Power Rating", value="240", unit="W", source="inferred"),
            ],
            applications=["Control cabinet power", "PLC power supply", "Sensor power", "Field device supply"],
            normalized_attributes={"output_voltage": "24 VDC", "output_current": "10 A", "input_voltage": "120/230 VAC"},
            source_evidence=[SourceEvidence(source_type="input", locator="short_description", excerpt="SITOP PSU200M power supply 24V 10A input 120/230VAC")],
            confidence=Confidence.high,
        ),
    },
    # 9. Temperature Controller
    {
        "input": ProductInput(
            manufacturer_part_number="E5CC-RX3A5M-000",
            brand="Omron",
            short_description="Digital temperature controller 100-240VAC relay output 48x48mm",
        ),
        "output": ProductIntelligence(
            manufacturer_part_number="E5CC-RX3A5M-000",
            brand="Omron",
            title="Omron E5CC-RX3A5M Digital Temperature Controller",
            category="Temperature Controllers",
            commerce_description=(
                "Omron E5CC compact digital temperature controller with 100-240 VAC "
                "supply, relay output, 48x48 mm panel-mount size, multi-input "
                "thermocouple and RTD support, and advanced PID auto-tuning."
            ),
            key_features=["48x48 mm DIN size", "Relay output", "Multi-input TC/RTD", "PID auto-tuning"],
            specifications=[
                ProductSpec(name="Supply Voltage", value="100-240", unit="VAC", source="extracted_spec"),
                ProductSpec(name="Panel Cutout", value="48x48", unit="mm", source="extracted_spec"),
            ],
            applications=["Plastic molding", "Heat treatment ovens", "Food processing", "Packaging machinery"],
            normalized_attributes={"supply_voltage": "100-240 VAC", "panel_cutout": "48x48 mm"},
            source_evidence=[SourceEvidence(source_type="input", locator="short_description", excerpt="Digital temperature controller 100-240VAC relay output 48x48mm")],
            confidence=Confidence.medium,
        ),
    },
    # 10. Industrial Relay Module
    {
        "input": ProductInput(
            manufacturer_part_number="700-HA33Z24",
            brand="Allen-Bradley",
            short_description="Ice cube relay 24VDC coil 11-pin 3PDT 10A 240VAC",
        ),
        "output": ProductIntelligence(
            manufacturer_part_number="700-HA33Z24",
            brand="Allen-Bradley",
            title="Allen-Bradley 700-HA33Z24 General Purpose Relay",
            category="Relays & Contactors",
            commerce_description=(
                "Allen-Bradley 700-HA33Z24 general purpose ice cube relay with 24 VDC "
                "coil, 3PDT contact configuration, 10 A contact rating at 240 VAC, "
                "11-pin octal base mount, and LED indicator."
            ),
            key_features=["24 VDC coil", "3PDT contacts", "10 A at 240 VAC", "11-pin octal base"],
            specifications=[
                ProductSpec(name="Coil Voltage", value="24", unit="VDC", source="extracted_spec"),
                ProductSpec(name="Contact Rating", value="10", unit="A", source="extracted_spec"),
                ProductSpec(name="Max Voltage", value="240", unit="VAC", source="extracted_spec"),
            ],
            applications=["Control panel logic", "Interlock circuits", "Motor starter auxiliaries", "HVAC controls"],
            normalized_attributes={"coil_voltage": "24 VDC", "contact_rating": "10 A", "contact_config": "3PDT"},
            source_evidence=[SourceEvidence(source_type="input", locator="short_description", excerpt="Ice cube relay 24VDC coil 11-pin 3PDT 10A 240VAC")],
            confidence=Confidence.medium,
        ),
    },
    # 11. Hydraulic Valve
    {
        "input": ProductInput(
            manufacturer_part_number="4WE6D6X/EG24N9K4",
            brand="Bosch Rexroth",
            short_description="Directional control valve 4/3 way 24VDC solenoid NG6 315 bar",
        ),
        "output": ProductIntelligence(
            manufacturer_part_number="4WE6D6X/EG24N9K4",
            brand="Bosch Rexroth",
            title="Bosch Rexroth 4WE6 Directional Control Valve",
            category="Hydraulic Valves",
            commerce_description=(
                "Bosch Rexroth 4WE6D6X directional control valve, 4/3-way solenoid "
                "operated with 24 VDC coil, NG6/D03 mounting pattern, 315 bar max "
                "working pressure, and center position spring return."
            ),
            key_features=["4/3-way configuration", "24 VDC solenoid", "NG6/D03 size", "315 bar max pressure"],
            specifications=[
                ProductSpec(name="Max Pressure", value="315", unit="bar", source="extracted_spec"),
                ProductSpec(name="Coil Voltage", value="24", unit="VDC", source="extracted_spec"),
                ProductSpec(name="Nominal Size", value="6", unit="mm", source="inferred"),
            ],
            applications=["Hydraulic presses", "Injection molding machines", "Mobile hydraulics", "Machine tools"],
            normalized_attributes={"max_pressure": "315 bar", "coil_voltage": "24 VDC"},
            source_evidence=[SourceEvidence(source_type="input", locator="short_description", excerpt="Directional control valve 4/3 way 24VDC solenoid NG6 315 bar")],
            confidence=Confidence.medium,
        ),
    },
    # 12. Industrial HMI Panel
    {
        "input": ProductInput(
            manufacturer_part_number="6AV2124-0GC01-0AX0",
            brand="Siemens",
            short_description="SIMATIC HMI TP700 Comfort 7 inch widescreen TFT display",
        ),
        "output": ProductIntelligence(
            manufacturer_part_number="6AV2124-0GC01-0AX0",
            brand="Siemens",
            title="Siemens SIMATIC HMI TP700 Comfort Panel 7-inch",
            category="HMI & Operator Panels",
            commerce_description=(
                "Siemens SIMATIC HMI TP700 Comfort Panel with 7-inch widescreen TFT "
                "touchscreen, 800x480 resolution, 16 million colors, PROFINET and MPI "
                "interfaces, and 12 MB user memory for plant visualization."
            ),
            key_features=["7-inch widescreen TFT", "Touch operation", "PROFINET + MPI", "12 MB user memory"],
            specifications=[
                ProductSpec(name="Display Size", value="7", unit="inch", source="extracted_spec"),
                ProductSpec(name="Resolution", value="800x480", unit="px", source="inferred"),
            ],
            applications=["Process visualization", "Machine operation", "Production monitoring", "Recipe management"],
            normalized_attributes={"display_size": "7 inch", "resolution": "800x480 px"},
            source_evidence=[SourceEvidence(source_type="input", locator="short_description", excerpt="SIMATIC HMI TP700 Comfort 7 inch widescreen TFT display")],
            confidence=Confidence.medium,
        ),
    },
    # 13. Safety Light Curtain
    {
        "input": ProductInput(
            manufacturer_part_number="C4C-SA06010A10000",
            brand="Sick",
            short_description="Safety light curtain type 4 sender 600mm 14mm resolution",
        ),
        "output": ProductIntelligence(
            manufacturer_part_number="C4C-SA06010A10000",
            brand="Sick",
            title="Sick C4C-SA Safety Light Curtain Sender",
            category="Safety Devices",
            commerce_description=(
                "Sick C4C-SA type 4 safety light curtain sender unit with 600 mm "
                "protective height, 14 mm finger detection resolution, SIL3/PLe "
                "rated, and rugged IP65 aluminum housing for machine safeguarding."
            ),
            key_features=["Type 4 / SIL3 / PLe", "600 mm protective height", "14 mm resolution", "IP65 housing"],
            specifications=[
                ProductSpec(name="Protective Height", value="600", unit="mm", source="extracted_spec"),
                ProductSpec(name="Resolution", value="14", unit="mm", source="extracted_spec"),
            ],
            applications=["Press safeguarding", "Robot cell entry", "Palletizer access", "Automated loading docks"],
            normalized_attributes={"protective_height": "600 mm", "resolution": "14 mm"},
            source_evidence=[SourceEvidence(source_type="input", locator="short_description", excerpt="Safety light curtain type 4 sender 600mm 14mm resolution")],
            confidence=Confidence.medium,
        ),
    },
    # 14. Industrial Ethernet Switch
    {
        "input": ProductInput(
            manufacturer_part_number="6GK5008-0BA10-1AB2",
            brand="Siemens",
            short_description="SCALANCE XB008 unmanaged industrial Ethernet switch 8 ports 10/100 Mbit",
        ),
        "output": ProductIntelligence(
            manufacturer_part_number="6GK5008-0BA10-1AB2",
            brand="Siemens",
            title="Siemens SCALANCE XB008 Unmanaged Ethernet Switch",
            category="Industrial Networking",
            commerce_description=(
                "Siemens SCALANCE XB008 unmanaged industrial Ethernet switch with 8 "
                "RJ45 ports at 10/100 Mbit/s, 24 VDC supply, compact DIN-rail mount, "
                "and IP20 rating for PROFINET and standard Ethernet networks."
            ),
            key_features=["8x RJ45 10/100 ports", "24 VDC supply", "DIN-rail mount", "PROFINET compatible"],
            specifications=[
                ProductSpec(name="Ports", value="8", unit=None, source="extracted_spec"),
                ProductSpec(name="Speed", value="10/100", unit="Mbit/s", source="extracted_spec"),
            ],
            applications=["PROFINET networks", "Machine connectivity", "Cabinet networking", "Factory LAN"],
            normalized_attributes={"ports": "8", "speed": "10/100 Mbit/s"},
            source_evidence=[SourceEvidence(source_type="input", locator="short_description", excerpt="SCALANCE XB008 unmanaged industrial Ethernet switch 8 ports 10/100 Mbit")],
            confidence=Confidence.medium,
        ),
    },
    # 15. Minimal / edge-case — no specs, low confidence
    {
        "input": ProductInput(
            manufacturer_part_number="UNKNOWN-001",
            brand="Generic",
            short_description="Industrial component",
        ),
        "output": ProductIntelligence(
            manufacturer_part_number="UNKNOWN-001",
            brand="Generic",
            title="Generic Industrial Component UNKNOWN-001",
            category="Unknown",
            commerce_description="Generic industrial component. Insufficient data to enrich.",
            key_features=[],
            specifications=[],
            applications=[],
            normalized_attributes={},
            source_evidence=[],
            quality_warnings=["Insufficient source data to produce confident enrichment."],
            confidence=Confidence.low,
        ),
    },
]


# ---------------------------------------------------------------------------
# Run evaluation across all products
# ---------------------------------------------------------------------------
def main() -> None:
    from product_agent.evaluation import configure_langsmith
    configure_langsmith()

    total_overall = 0.0
    pass_count = 0
    fail_count = 0

    print(f"{'#':<4} {'MPN':<28} {'Brand':<22} {'Category':<30} {'Overall':>8}  Rubric Breakdown")
    print("=" * 140)

    for idx, entry in enumerate(TEST_PRODUCTS, 1):
        product_input: ProductInput = entry["input"]
        product_output: ProductIntelligence = entry["output"]

        scores = evaluate_product_output(product_input, product_output)
        overall = next(s for s in scores if s.key == "overall")
        rubric_parts = [f"{s.key}={s.score:.2f}" for s in scores if s.key != "overall"]

        status_icon = "✅" if overall.score >= 0.5 else "⚠️"
        print(f"{idx:<4} {product_input.manufacturer_part_number:<28} {product_input.brand:<22} {product_output.category:<30} {overall.score:>7.2f}  {', '.join(rubric_parts)}")

        # Validate schema round-trip
        req = EvaluationRequest(product_input=product_input, output=product_output)
        assert req.product_input.manufacturer_part_number == product_input.manufacturer_part_number

        # Validate score sanity
        assert len(scores) == 8, f"Product #{idx}: expected 8 scores, got {len(scores)}"
        assert all(0.0 <= s.score <= 1.0 for s in scores), f"Product #{idx}: score out of range"

        total_overall += overall.score
        if overall.score >= 0.5:
            pass_count += 1
        else:
            fail_count += 1

    avg = total_overall / len(TEST_PRODUCTS)
    print("=" * 140)
    print(f"\n📊 Summary: {len(TEST_PRODUCTS)} products evaluated  |  ✅ Passed: {pass_count}  |  ⚠️ Low-score: {fail_count}  |  Average overall: {avg:.2f}")

    if avg >= 0.5:
        print(f"\n✅ Evaluation smoke test PASSED — average overall score: {avg:.2f}")
    else:
        print(f"\n❌ Evaluation smoke test FAILED — average overall score: {avg:.2f}")
        sys.exit(1)


if __name__ == "__main__":
    main()
