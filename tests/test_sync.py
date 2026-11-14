import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

from wikisync.config import Config, ConfigError
from wikisync.source import read_tree
from wikisync.sync import run
from tests.helpers import FakeClient, make_config, make_tarball

FILES = {
    "README.md": "# Home\n[p](p/index.md)\n",
    "p/index.md": "# P\n",
    "p/sub/a0010-x.md": "# X\n[zurück](../index.md)\n",
    "scripts/tool.py": "x",
    "CLAUDE.md": "intern",
    ".github/workflows/ci.yml": "x",
}


def fetch_files(files):
    return lambda owner, repo, branch, token: make_tarball(files)


def execute(config, client, files=FILES):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = run(config, fetch=fetch_files(files), client=client)
    return code, out.getvalue(), err.getvalue()


class SourceTests(unittest.TestCase):
    def test_exclude_and_split(self):
        tree = read_tree(make_tarball(FILES), ("scripts/**", "CLAUDE.md", ".github/**"))
        self.assertEqual(sorted(tree.markdown), ["README.md", "p/index.md", "p/sub/a0010-x.md"])
        self.assertEqual(tree.others, frozenset())


class RunTests(unittest.TestCase):
    def setUp(self):
        self.config = make_config(exclude=("scripts/**", "CLAUDE.md", ".github/**"))

    def test_creates_all_then_is_idempotent(self):
        client = FakeClient()
        code, out, _ = execute(self.config, client)
        self.assertEqual(code, 0)
        self.assertEqual(sorted(path for action, path in client.calls if action == "create"), ["docs", "docs/p", "docs/p/sub", "docs/p/sub/a0010-x"])
        self.assertEqual(sorted(path for action, path in client.calls if action == "render"), ["docs", "docs/p", "docs/p/sub", "docs/p/sub/a0010-x"])
        self.assertEqual(client.pages["docs/p/sub/a0010-x"]["title"], "a0010 - X")
        self.assertIn("(/en/docs/p)", client.pages["docs/p/sub/a0010-x"]["content"])
        client.calls.clear()
        code, out, _ = execute(self.config, client)
        self.assertEqual(code, 0)
        self.assertEqual(client.calls, [])
        self.assertIn("unverändert=4", out)

    def test_update_only_changed(self):
        client = FakeClient()
        execute(self.config, client)
        client.calls.clear()
        changed = dict(FILES, **{"p/index.md": "# P neu\n"})
        execute(self.config, client, changed)
        self.assertEqual(client.calls, [("update", "docs/p"), ("render", "docs/p")])

    def test_deletes_removed_sources_only_under_prefix(self):
        client = FakeClient({"other/page": {"title": "o", "content": "o", "description": ""}})
        execute(self.config, client)
        client.calls.clear()
        trimmed = {name: text for name, text in FILES.items() if name != "p/sub/a0010-x.md"}
        execute(self.config, client, trimmed)
        self.assertEqual(sorted(client.calls), [("delete", "docs/p/sub"), ("delete", "docs/p/sub/a0010-x")])
        self.assertIn("other/page", client.pages)

    def test_legacy_prefix_removed(self):
        client = FakeClient({"Github/capulus-core/docs/x": {"title": "o", "content": "o", "description": ""}})
        config = make_config(exclude=self.config.exclude, legacy_prefixes=("Github/capulus-core",))
        execute(config, client)
        self.assertNotIn("Github/capulus-core/docs/x", client.pages)

    def test_dry_run_changes_nothing(self):
        client = FakeClient({"docs/old": {"title": "o", "content": "o", "description": ""}})
        config = make_config(exclude=self.config.exclude, dry_run=True)
        code, out, _ = execute(config, client)
        self.assertEqual(code, 0)
        self.assertEqual(client.calls, [])
        self.assertIn("[CREATE]", out)
        self.assertIn("[DELETE] /en/docs/old", out)

    def test_too_few_pages_aborts_without_changes(self):
        client = FakeClient({"docs/old": {"title": "o", "content": "o", "description": ""}})
        config = make_config(exclude=self.config.exclude, min_pages=50)
        code, _, err = execute(config, client)
        self.assertEqual(code, 1)
        self.assertEqual(client.calls, [])
        self.assertIn("mindestens 50", err)

    def test_fetch_failure_changes_nothing(self):
        client = FakeClient({"docs/old": {"title": "o", "content": "o", "description": ""}})
        def broken(*args):
            raise OSError("offline")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = run(self.config, fetch=broken, client=client)
        self.assertEqual(code, 1)
        self.assertEqual(client.calls, [])


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.config = make_config(exclude=("scripts/**", "CLAUDE.md", ".github/**"))

    def test_budget_defers_creates(self):
        client = FakeClient()
        code, out, _ = execute(make_config(exclude=self.config.exclude, render_batch=2), client)
        self.assertEqual(code, 0)
        self.assertEqual(len([call for call in client.calls if call[0] == "create"]), 2)
        self.assertIn("zurückgestellt=2", out)
        for _ in range(2):
            execute(make_config(exclude=self.config.exclude, render_batch=2), client)
        self.assertEqual(len(client.pages), 4)

    def test_budget_defers_updates_and_keeps_old_content(self):
        client = FakeClient()
        execute(self.config, client)
        client.calls.clear()
        changed = dict(FILES, **{"p/index.md": "# P neu\n", "README.md": "# Home neu\n"})
        limited = make_config(exclude=self.config.exclude, render_batch=1)
        code, out, _ = execute(limited, client, changed)
        self.assertEqual(len([call for call in client.calls if call[0] == "update"]), 1)
        self.assertIn("zurückgestellt=1", out)
        execute(limited, client, changed)
        self.assertEqual(len([call for call in client.calls if call[0] == "update"]), 2)

    def test_page_without_render_is_rendered_again(self):
        client = FakeClient()
        execute(self.config, client)
        client.pages["docs/p"]["render"] = ""
        client.calls.clear()
        code, out, _ = execute(self.config, client)
        self.assertEqual(code, 0)
        self.assertEqual(client.calls, [("render", "docs/p")])
        self.assertIn("[RENDER] /en/docs/p", out)

    def test_render_limit_is_not_an_error_and_heals_next_run(self):
        client = FakeClient(render_limit=1)
        code, _, err = execute(self.config, client)
        self.assertEqual(code, 0)
        self.assertIn("Render-Limit", err)
        client.render_limit = None
        client.calls.clear()
        execute(self.config, client)
        self.assertTrue(all(page["render"] for page in client.pages.values()))

    def test_dry_run_queues_no_render(self):
        client = FakeClient()
        execute(make_config(exclude=self.config.exclude, dry_run=True), client)
        self.assertEqual(client.calls, [])


class ConfigTests(unittest.TestCase):
    def test_required(self):
        with self.assertRaises(ConfigError):
            Config.from_env({})

    def test_defaults_and_lists(self):
        config = Config.from_env({"WIKIJS_API_URL": "http://w/", "WIKIJS_API_TOKEN": "t", "WIKIJS_LEGACY_PREFIXES": "Github/capulus-core, x/"})
        self.assertEqual(config.api_url, "http://w")
        self.assertEqual(config.prefix, "docs")
        self.assertEqual(config.legacy_prefixes, ("Github/capulus-core", "x"))
        self.assertIn("capulus-core/archiv/**", config.exclude)
        self.assertFalse(config.dry_run)
        self.assertEqual(config.site_id, "")
        self.assertEqual(config.render_batch, 8)

    def test_site_and_render_batch(self):
        config = Config.from_env({"WIKIJS_API_URL": "http://w", "WIKIJS_API_TOKEN": "t", "WIKIJS_SITE_ID": " abc ", "RENDER_BATCH": "3"})
        self.assertEqual(config.site_id, "abc")
        self.assertEqual(config.render_batch, 3)

    def test_render_batch_invalid(self):
        for value in ("x", "0"):
            with self.assertRaises(ConfigError):
                Config.from_env({"WIKIJS_API_URL": "http://w", "WIKIJS_API_TOKEN": "t", "RENDER_BATCH": value})


if __name__ == "__main__":
    unittest.main()
