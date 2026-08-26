import unittest
from unittest.mock import MagicMock, patch

from app.llm.providers import guess_provider, is_chat_model, list_models, suggest_base_url


class TestGuessProvider(unittest.TestCase):
    def test_anthropic_prefix_wins(self):
        self.assertEqual(guess_provider("sk-ant-abc", None, "openai"), "anthropic")

    def test_openrouter_prefix(self):
        self.assertEqual(guess_provider("sk-or-v1-abc", None, "openai"), "compatible")
        self.assertEqual(suggest_base_url("sk-or-v1-abc"), "https://openrouter.ai/api/v1")

    def test_groq_prefix(self):
        self.assertEqual(guess_provider("gsk_abc", None, "openai"), "compatible")
        self.assertEqual(suggest_base_url("gsk_abc"), "https://api.groq.com/openai/v1")

    def test_base_url_means_compatible(self):
        self.assertEqual(guess_provider("sk-abc", "https://api.groq.com/openai/v1", "openai"), "compatible")

    def test_openai_default(self):
        self.assertEqual(guess_provider("sk-proj-abc", None, "openai"), "openai")


class TestChatFilter(unittest.TestCase):
    def test_keeps_gpt(self):
        self.assertTrue(is_chat_model("gpt-4.1-mini", strict=True))
        self.assertTrue(is_chat_model("o4-mini", strict=True))

    def test_drops_whisper(self):
        self.assertFalse(is_chat_model("whisper-1", strict=True))
        self.assertFalse(is_chat_model("text-embedding-3-small", strict=True))

    def test_compatible_keeps_llama(self):
        self.assertTrue(is_chat_model("llama-3.1-70b", strict=False))


class TestListModels(unittest.TestCase):
    def test_openai_filters_non_chat(self):
        fake = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "data": [
                {"id": "gpt-4.1-mini"},
                {"id": "whisper-1"},
                {"id": "text-embedding-3-large"},
            ]
        }
        fake.get.return_value = resp
        with patch.dict("sys.modules", {"httpx": fake}):
            models = list_models("openai", "sk-test", None)
        self.assertEqual([m["id"] for m in models], ["gpt-4.1-mini"])

    def test_anthropic_uses_display_name(self):
        fake = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "data": [{"id": "claude-sonnet-4-6", "display_name": "Claude Sonnet 4.6"}]
        }
        fake.get.return_value = resp
        with patch.dict("sys.modules", {"httpx": fake}):
            models = list_models("anthropic", "sk-ant-test", None)
        self.assertEqual(models, [{"id": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6"}])

    def test_http_error_message(self):
        fake = MagicMock()
        resp = MagicMock()
        resp.status_code = 401
        resp.json.return_value = {"error": {"message": "Incorrect API key provided"}}
        fake.get.return_value = resp
        with patch.dict("sys.modules", {"httpx": fake}):
            with self.assertRaises(RuntimeError) as ctx:
                list_models("openai", "sk-bad", None)
        self.assertIn("Incorrect API key", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
