"""Tests for storage layer."""

import json
import pytest
from pathlib import Path

from cogmem.storage.filesystem import MemoryDir, REPO_SUBDIRS
from cogmem.storage.index import KeywordIndex, extract_keywords


class TestMemoryDir:
    def test_ensure_dirs(self, tmp_path):
        md = MemoryDir(tmp_path / ".memory")
        md.ensure_dirs(REPO_SUBDIRS)
        assert md.exists
        for sub in REPO_SUBDIRS:
            assert (tmp_path / ".memory" / sub).is_dir()

    def test_write_read_json(self, tmp_path):
        md = MemoryDir(tmp_path / ".memory")
        md.ensure_dirs()
        md.write_json("meta.json", {"version": "3.1", "count": 42})
        data = md.read_json("meta.json")
        assert data["version"] == "3.1"
        assert data["count"] == 42

    def test_read_json_missing(self, tmp_path):
        md = MemoryDir(tmp_path / ".memory")
        assert md.read_json("nonexistent.json") == {}

    def test_write_read_text(self, tmp_path):
        md = MemoryDir(tmp_path / ".memory")
        md.ensure_dirs()
        md.write_text("spatial.md", "# Spatial\nSome content")
        text = md.read_text("spatial.md")
        assert "Spatial" in text

    def test_write_read_markdown(self, tmp_path):
        md = MemoryDir(tmp_path / ".memory")
        md.ensure_dirs()
        md.write_markdown("test.md", {"title": "Test", "count": 5}, "Body text")
        meta, body = md.read_markdown("test.md")
        assert meta["title"] == "Test"
        assert "Body text" in body

    def test_list_files(self, tmp_path):
        md = MemoryDir(tmp_path / ".memory")
        md.ensure_dirs()
        (tmp_path / ".memory" / "episodes" / "ep1.md").write_text("content")
        (tmp_path / ".memory" / "episodes" / "ep2.md").write_text("content")
        files = md.list_files("episodes")
        assert len(files) == 2

    def test_delete_file(self, tmp_path):
        md = MemoryDir(tmp_path / ".memory")
        md.ensure_dirs()
        md.write_text("test.md", "hello")
        assert md.file_exists("test.md")
        assert md.delete_file("test.md")
        assert not md.file_exists("test.md")
        assert not md.delete_file("test.md")  # already gone


class TestKeywordIndex:
    def test_add_and_query(self):
        idx = KeywordIndex()
        idx.add_entry(["auth", "login", "timeout"], "episodes/ep1.md")
        idx.add_entry(["auth", "password"], "episodes/ep2.md")

        results = idx.query(["auth"])
        assert len(results) == 2

        results = idx.query(["auth", "login"])
        # ep1 matches both, ep2 matches one
        assert results[0][0] == "episodes/ep1.md"
        assert results[0][1] == 2

    def test_remove_entry(self):
        idx = KeywordIndex()
        idx.add_entry(["auth", "login"], "episodes/ep1.md")
        idx.remove_entry("episodes/ep1.md")
        results = idx.query(["auth"])
        assert len(results) == 0

    def test_save_load(self, tmp_path):
        idx = KeywordIndex()
        idx.add_entry(["foo", "bar"], "ref1.md")
        path = tmp_path / "index.json"
        idx.save(path)

        loaded = KeywordIndex.load(path)
        results = loaded.query(["foo"])
        assert len(results) == 1

    def test_all_refs(self):
        idx = KeywordIndex()
        idx.add_entry(["a"], "ref1")
        idx.add_entry(["b"], "ref2")
        assert idx.all_refs() == {"ref1", "ref2"}

    def test_no_duplicates(self):
        idx = KeywordIndex()
        idx.add_entry(["auth"], "ep1.md")
        idx.add_entry(["auth"], "ep1.md")
        results = idx.query(["auth"])
        assert results[0][1] == 1  # only counted once


class TestExtractKeywords:
    def test_basic(self):
        kws = extract_keywords("Fixed the authentication timeout bug")
        assert "fixed" in kws
        assert "authentication" in kws
        assert "timeout" in kws
        assert "bug" in kws
        assert "the" not in kws

    def test_file_paths(self):
        kws = extract_keywords("auth/login.py handler.js")
        assert "auth" in kws
        assert "login" in kws

    def test_short_words_filtered(self):
        kws = extract_keywords("a b cd the")
        assert len(kws) == 0
