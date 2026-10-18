import csv
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from packet_def import PACKET_SIZE, unpack_raw_packet
from current_sensing import measure_current
import config
try:
    import serial
except ModuleNotFoundError:
    # Offline tests inject SerialStub below; no real port is opened.
    with patch.dict(sys.modules, {'serial': types.ModuleType('serial')}):
        from telemetry_engine import TelemetryEngine
else:
    from telemetry_engine import TelemetryEngine


# Hand-authored wire bytes, independent of PACKET_FORMAT:
# shunt A=0, B=32768, C=65535; BEMF=-123; tail at offset 26.
WIRE = bytes.fromhex(
    "aa 34 12 51 85 ff 64 00 96 00 7d 00 c8 00 32 00 "
    "03 7c 00 02 00 00 00 80 ff ff bb"
)


class ShuntTelemetryTests(unittest.TestCase):
    def test_unsigned_fields_and_existing_offsets(self):
        self.assertEqual(PACKET_SIZE, 27)
        pkt = unpack_raw_packet(WIRE)
        self.assertEqual((pkt['shunt_a'], pkt['shunt_b'], pkt['shunt_c']),
                         (0, 32768, 65535))
        self.assertEqual((pkt['ccr'], pkt['bemf_curr'], pkt['ts_tim'],
                          pkt['cnt_ic'], pkt['tail']),
                         (0x1234, -123, 124, 2, 0xBB))

    def test_receive_and_csv_exports(self):
        engine = TelemetryEngine()
        stream = bytearray()
        for step in range(1, 7):
            packet = bytearray(WIRE)
            packet[3] = 0x50 | step
            packet[20:26] = bytes.fromhex('e8 03 d0 07 b8 0b')  # 1000, 2000, 3000
            stream.extend(packet)

        class SerialStub:
            def read(self, count):
                result = bytes(stream[:count])
                del stream[:count]
                if not stream:
                    engine.is_running = False
                return result

        engine.ser = SerialStub()
        engine.set_recording(True)
        engine.is_running = True
        engine._rx_worker()
        self.assertEqual(engine.stats['total_recv'], 6)
        self.assertEqual(engine.stats['sync_err'], 0)
        self.assertEqual(engine.stats['shunt_b'], 2000)
        self.assertEqual(engine.stats['shunt_c'], 3000)
        self.assertEqual(engine.stats['current_sample']['low_side_phase'], 'B')

        previous_dir = os.getcwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                for path in (engine.export_raw_csv('TEST'),
                             engine.export_sequence_csv()):
                    self.assertIsNotNone(path)
                    with open(path, newline='', encoding='utf-8-sig') as source:
                        rows = list(csv.DictReader(source))
                    self.assertEqual(len(rows), 6)
                    for row, phase, raw in zip(rows, 'BCCAAB', (2000, 3000, 3000, 1000, 1000, 2000)):
                        self.assertEqual(
                            [row[key] for key in ('shunt_a', 'shunt_b', 'shunt_c')],
                            ['1000', '2000', '3000'])
                        self.assertEqual(row['low_side_phase'], phase)
                        self.assertAlmostEqual(float(row['current_a']), raw * 3.3 / 4095)
                        self.assertEqual(row['current_status'], 'ESTIMATE')
            finally:
                os.chdir(previous_dir)

    def test_calibration_and_rails(self):
        pkt = dict(step=1, shunt_a=100, shunt_b=1241, shunt_c=300)
        self.assertAlmostEqual(measure_current(pkt)['current_a'], 1.0, places=3)
        with patch.dict(config.SHUNT_ZERO_ADC, B=100):
            self.assertAlmostEqual(measure_current(pkt)['current_a'], 1141 * 3.3 / 4095)
            self.assertLess(measure_current({**pkt, 'shunt_b': 50})['current_a'], 0)
        for raw, status in ((0, 'ADC_LOW_RAIL'), (4095, 'ADC_HIGH_RAIL'),
                            (4096, 'ADC_OUT_OF_RANGE'), (65535, 'ADC_OUT_OF_RANGE')):
            result = measure_current({**pkt, 'shunt_b': raw})
            self.assertEqual(result['current_status'], status)
            if raw > 4095:
                self.assertIsNone(result['current_a'])
        for step in (0, 7, 15):
            result = measure_current({**pkt, 'step': step})
            self.assertEqual(result['current_status'], 'INVALID_STEP')
            self.assertIsNone(result['current_a'])


if __name__ == '__main__':
    unittest.main()
