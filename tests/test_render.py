import unittest

from wikisync.render import CollisionError, build_pages, page_title, rewrite_links, wiki_path
from wikisync.source import Tree
from tests.helpers import make_config


class PathTests(unittest.TestCase):
    def setUp(self):
        self.config = make_config()

    def test_paths(self):
        self.assertEqual(wiki_path(self.config, "README.md"), "docs")
        self.assertEqual(wiki_path(self.config, "capulus-core/index.md"), "docs/capulus-core")
        self.assertEqual(wiki_path(self.config, "capulus-core/3-apps/300d0-carplay-api.md"), "docs/capulus-core/3-apps/300d0-carplay-api")
        self.assertEqual(wiki_path(self.config, "x/Datei mit.Punkt.md"), "docs/x/Datei-mit-Punkt")

    def test_title_numbered(self):
        self.assertEqual(page_title("a/a0000-ubuntu.md", "# Ubuntu\n"), "a0000 - Ubuntu")
        self.assertEqual(page_title("a/a0000-ubuntu.md", "# a0000 Ubuntu\n"), "a0000 Ubuntu")
        self.assertEqual(page_title("a/other.md", "kein Titel"), "other")
        self.assertEqual(page_title("proj/index.md", "text"), "proj")

    def test_title_ignores_fenced_heading(self):
        self.assertEqual(page_title("a/x.md", "```\n# nicht\n```\n# echt\n"), "echt")


class LinkTests(unittest.TestCase):
    def setUp(self):
        self.config = make_config()
        markdown = {
            "p/index.md": "# P",
            "p/a/one.md": "# One",
            "p/a/two.md": "# Two",
            "q/index.md": "# Q",
        }
        self.tree = Tree.of(markdown, {"p/pics/menu.png", "p/data.json"})

    def rewrite(self, text, source="p/a/one.md"):
        return rewrite_links(self.config, self.tree, source, text)

    def test_page_link_with_anchor(self):
        self.assertEqual(self.rewrite("[x](two.md#abschnitt)"), "[x](/en/docs/p/a/two#abschnitt)")

    def test_cross_project_and_index(self):
        self.assertEqual(self.rewrite("[x](../../q/index.md)"), "[x](/en/docs/q)")

    def test_directory_link(self):
        self.assertEqual(self.rewrite("[x](../a/)"), "[x](/en/docs/p/a)")

    def test_image_and_file(self):
        self.assertEqual(self.rewrite("![i](../pics/menu.png)"), "![i](https://raw.githubusercontent.com/pkr-lab/pkr-lab-docs/main/p/pics/menu.png)")
        self.assertEqual(self.rewrite("[d](../data.json)"), "[d](https://github.com/pkr-lab/pkr-lab-docs/blob/main/p/data.json)")

    def test_html_attributes(self):
        self.assertEqual(
            self.rewrite('<img src="../pics/menu.png" alt="m">'),
            '<img src="https://raw.githubusercontent.com/pkr-lab/pkr-lab-docs/main/p/pics/menu.png" alt="m">',
        )

    def test_untouched(self):
        for text in ("[x](https://example.org)", "[x](#anker)", "[x](mailto:a@b.de)", "[x](fehlt.md)", "[x](/abs/pfad)"):
            self.assertEqual(self.rewrite(text), text)

    def test_code_is_untouched(self):
        self.assertEqual(self.rewrite("`[x](two.md)` und [y](two.md)"), "`[x](two.md)` und [y](/en/docs/p/a/two)")
        fenced = "```\n[x](two.md)\n```"
        self.assertEqual(self.rewrite(fenced), fenced)

    def test_link_text_with_code_span(self):
        self.assertEqual(self.rewrite("[`two`](two.md)"), "[`two`](/en/docs/p/a/two)")

    def test_escaping_root(self):
        self.assertEqual(self.rewrite("[x](../../../../etc/passwd)"), "[x](../../../../etc/passwd)")


class BuildTests(unittest.TestCase):
    def test_index_pages_are_generated(self):
        config = make_config()
        pages = build_pages(config, Tree.of({"README.md": "# Home", "p/index.md": "# P", "p/a/one.md": "# One", "p/a/two.md": "# Two"}))
        self.assertEqual(sorted(pages), ["docs", "docs/p", "docs/p/a", "docs/p/a/one", "docs/p/a/two"])
        generated = pages["docs/p/a"]
        self.assertIn("[One](/en/docs/p/a/one)", generated.content)
        self.assertIn("automatisch", generated.content)
        self.assertEqual(generated.description, "Automatisch erzeugte Übersicht")
        self.assertEqual(pages["docs/p/a/one"].description, "Quelle: pkr-lab/pkr-lab-docs/p/a/one.md")

    def test_root_overview_generated_without_readme(self):
        pages = build_pages(make_config(), Tree.of({"p/index.md": "# P"}))
        self.assertIn("docs", pages)
        self.assertIn("[p](/en/docs/p)", pages["docs"].content)

    def test_collision(self):
        with self.assertRaises(CollisionError):
            build_pages(make_config(), Tree.of({"a-b.md": "x", "a b.md": "y"}))


if __name__ == "__main__":
    unittest.main()
