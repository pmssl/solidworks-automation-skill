"""Offline contracts for native persistent references."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.sw_entity_reference import (
    PersistentEntityReference,
    create_persistent_reference,
    resolve_persistent_reference,
)


class Extension:
    def __init__(self, entity): self.entity = entity
    def GetPersistReference3(self, entity): return (1, 2, 255) if entity is self.entity else ()
    def GetObjectByPersistReference3(self, payload, error):
        error.value = 0 if bytes(payload.value) == bytes((1, 2, 255)) else 1
        return self.entity


class Model:
    def __init__(self, entity): self.Extension = Extension(entity)


class PersistentReferenceTests(unittest.TestCase):
    def test_reference_round_trips_through_serializable_payload(self):
        entity = object(); model = Model(entity)
        reference = create_persistent_reference(model, entity)
        self.assertEqual(reference.to_bytes(), bytes((1, 2, 255)))
        restored = PersistentEntityReference(**reference.to_dict())
        result = resolve_persistent_reference(model, restored)
        self.assertIs(result["entity"], entity)
        self.assertEqual(result["error_code"], 0)

    def test_empty_reference_is_rejected(self):
        model = Model(object())
        with self.assertRaises(ValueError): create_persistent_reference(model, None)


if __name__ == "__main__":
    unittest.main()
