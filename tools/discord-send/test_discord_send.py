"""Local-only target-discovery regressions. Never queues or sends a message."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

LOADER = importlib.machinery.SourceFileLoader("discord_send", str(Path(__file__).with_name("discord-send")))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
send = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(send)


class KnownTargetsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.path.expanduser("~/.hermes/cache/scratch"))
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.home_patch = patch.object(send, "HOME", str(self.home))
        self.home_patch.start()
        self.addCleanup(self.home_patch.stop)

    def test_explicit_discord_route_needs_no_prior_conversation(self):
        (self.home / "channel_directory.json").write_text(json.dumps({
            "platforms": {"discord": [{"id": "200000000000000010", "type": "channel"}]}
        }))
        (self.home / "config.yaml").write_text(
            "gateway:\n  profile_routes:\n"
            "    - name: team-thread-qa\n      platform: discord\n"
            "      guild_id: '200000000000000020'\n"
            "      chat_id: '200000000000000010'\n"
            "      thread_id: '200000000000000030'\n      profile: team-qa\n"
        )
        self.assertEqual(send.known_targets(), {"200000000000000010", "200000000000000030"})


    def write_routes(self, routes):
        import yaml
        (self.home / "channel_directory.json").write_text(json.dumps({
            "platforms": {"discord": [{"id": "200000000000000010"}]}
        }))
        (self.home / "config.yaml").write_text(yaml.safe_dump({"gateway": {"profile_routes": routes}}))

    def test_unrelated_disabled_or_unknown_parent_routes_are_not_targets(self):
        base = {"platform": "discord", "profile": "team-qa", "chat_id": "200000000000000010"}
        variants = [
            {"platform": "telegram"}, {"enabled": False}, {"enabled": "false"},
            {"bot_profile": "other"}, {"profile": ""}, {"chat_id": "999999999999999999"},
            {"thread_id": True}, {"thread_id": 1.5}, {"thread_id": "123:123"},
            {"thread_id": "\u0661\u0662\u0663"}, {"thread_id": " 123"},
        ]
        routes = [dict(base, thread_id=str(200000000000000000 + i), **{k: v for k, v in variant.items() if k != "thread_id"})
                  for i, variant in enumerate(variants)]
        for route, variant in zip(routes, variants):
            route.update(variant)
        routes += ["not a route", None, {"platform": "discord", "guild_id": "777", "user_id": "888"}]
        self.write_routes(routes)
        self.assertEqual(send.known_targets(), {"200000000000000010"})

    def test_config_cannot_chain_unknown_parent_threads(self):
        self.write_routes([
            {"platform": "discord", "profile": "team-qa", "chat_id": "200000000000000010", "thread_id": "555"},
            {"platform": "discord", "profile": "team-qa", "chat_id": "555", "thread_id": "666"},
        ])
        self.assertEqual(send.known_targets(), {"200000000000000010", "555"})

    def test_broken_config_preserves_existing_directory_targets(self):
        self.write_routes([])
        for content in ("gateway: [", "[]", "gateway: []", "gateway:\n  profile_routes: invalid\n", ""):
            with self.subTest(content=content):
                (self.home / "config.yaml").write_text(content)
                self.assertEqual(send.known_targets(), {"200000000000000010"})

    def test_no_yaml_dependency_preserves_existing_targets(self):
        self.write_routes([])
        with patch.dict("sys.modules", {"yaml": None}):
            self.assertEqual(send.known_targets(), {"200000000000000010"})


if __name__ == "__main__":
    unittest.main()
