import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "docker-entrypoint.sh"
ENV_EXAMPLE = ROOT / ".env.example"


class DockerEntrypointConfigTests(unittest.TestCase):
    def test_entrypoint_persists_env_file_in_data_volume(self):
        script = ENTRYPOINT.read_text()
        self.assertIn("/data/.env", script)
        self.assertIn("ln -sf /data/.env /app/.env", script)
        self.assertIn("python /app/generate_jwt_secret.py", script)

    def test_entrypoint_uses_private_permissions_for_secret_files(self):
        script = ENTRYPOINT.read_text()
        self.assertIn("chmod 600 /data/.env /data/cookies.jar /data/credentials.json /data/blacklist.json", script)
        self.assertIn("chmod 644 /data/settings.json", script)

    def test_env_example_uses_current_stack_variables(self):
        env = ENV_EXAMPLE.read_text()
        self.assertIn("PORT=8080", env)
        self.assertIn("TZ=UTC", env)
        self.assertNotIn("WEB_PORT=", env)
        self.assertNotIn("DOCKER_REGISTRY=", env)


if __name__ == "__main__":
    unittest.main()
