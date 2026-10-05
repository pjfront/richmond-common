import base64
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("richmond_local_runner", Path(__file__).with_name("run_local.py"))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class LocalRunnerSecurityTests(unittest.TestCase):
    def test_child_environment_excludes_existing_cloud_credentials(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-provider-key", "SUPABASE_SERVICE_ROLE_KEY": "test-cloud-key", "RESEND_API_KEY": "test-mail-key", "API_SECRET": "test-webhook-key", "PATH": "test-path"}, clear=True):
            self.assertEqual(runner.safe_env(), {"PATH": "test-path"})

    def test_local_role_tokens_have_correct_signature_role_and_expiry(self):
        for role in ("anon", "service_role"):
            token = runner.token("test-local-signing-secret", role, 1234)
            header, payload, signature = token.split(".")
            decoded = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
            self.assertEqual(decoded["role"], role)
            self.assertEqual(decoded["iss"], "richmond-local-archive")
            self.assertEqual(decoded["exp"], 1234 + 365 * 86400)
            expected = runner.b64(hmac.new(b"test-local-signing-secret", f"{header}.{payload}".encode(), hashlib.sha256).digest())
            self.assertEqual(signature, expected)

    def test_paths_target_the_dedicated_runtime_and_preserved_cluster(self):
        self.assertEqual(runner.DEFAULT_RUNTIME.parent, runner.WORKSPACE)
        self.assertEqual(runner.DEFAULT_RUNTIME.name, "local-runtime")
        self.assertEqual(runner.CLUSTER.parent.name, "restore-test")
        self.assertEqual(runner.PG_BIN.parent.name, "pgsql")


if __name__ == "__main__":
    unittest.main()
