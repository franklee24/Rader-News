#!/usr/bin/env python3
"""Offline contract tests for AI client and scoring fallback."""
import os
import sys
import unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import ai_client

class AIClientContractTests(unittest.TestCase):
    def test_disabled_without_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(ai_client.configured())
            with self.assertRaisesRegex(RuntimeError,"AI disabled"):
                ai_client.chat_json("system", {"items":[]})

    def test_enabled_when_key_and_model_present(self):
        with patch.dict(os.environ, {"AI_API_KEY":"test-key","AI_MODEL":"test-model"}, clear=True):
            self.assertTrue(ai_client.configured())

if __name__=="__main__":
    unittest.main()
