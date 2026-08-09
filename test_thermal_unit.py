
import unittest
from unittest.mock import patch
import sys, os
sys.path.insert(0, os.path.expanduser("~/cinek_automatico"))
from thermal import GateTermico, SENSOR_PATH

class TestThermal(unittest.TestCase):
    def test_sensor_real_returns_float(self):
        """El sensor real debe devolver un float o None."""
        g = GateTermico()
        temp = g.leer()
        if temp is not None:
            self.assertIsInstance(temp, float)
            self.assertGreater(temp, 0.0)
            print(f"Sensor vivo: {temp}°C")

    def test_no_sensor_blocks_gate(self):
        """Sin sensor, leer() devuelve None (NO_DATA)."""
        g = GateTermico(sensor_path=None)
        temp = g.leer()
        self.assertIsNone(temp)

if __name__ == "__main__":
    unittest.main(verbosity=2)
