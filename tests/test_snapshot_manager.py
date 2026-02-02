import unittest
import sys
import os
import re
from pathlib import Path
import tempfile
import time
from unittest.mock import MagicMock, patch

# Add scripts directory to path to allow importing snapshot_manager
sys.path.append(str(Path(__file__).parent.parent / "scripts"))

from snapshot_manager import SkillSnapshotManager, SnapshotError


class TestSkillSnapshotManager(unittest.TestCase):

    def setUp(self):
        # Setup patchers
        self.patcher_which = patch("shutil.which")
        self.patcher_home = patch("pathlib.Path.home")
        self.patcher_env = patch("os.environ.copy")

        mock_which = self.patcher_which.start()
        mock_home = self.patcher_home.start()
        mock_env = self.patcher_env.start()

        # Mock environment
        mock_env.return_value = {}
        # Mock home directory
        self.mock_home_path = Path("/mock/home")
        mock_home.return_value = self.mock_home_path
        # Mock tools existence
        mock_which.side_effect = lambda x: f"/bin/{x}"

        # Patch the _find_skills_dir method to avoid filesystem lookups during init
        self.patcher_find = patch.object(SkillSnapshotManager, "_find_skills_dir")
        mock_find_dir = self.patcher_find.start()
        mock_find_dir.return_value = self.mock_home_path / ".claude/skills"

        self.manager = SkillSnapshotManager()

    def tearDown(self):
        patch.stopall()

    def test_version_tag_regex(self):
        """Test regex logic for parsing version tags"""
        skill_name = "my-skill"
        pattern = re.compile(rf"^{re.escape(skill_name)}/v(\d+)$")

        # Match valid tags
        match1 = pattern.match("my-skill/v1")
        self.assertIsNotNone(match1)
        self.assertEqual(match1.group(1), "1")

        match2 = pattern.match("my-skill/v105")
        self.assertIsNotNone(match2)
        self.assertEqual(match2.group(1), "105")

        # Fail invalid tags
        self.assertIsNone(pattern.match("other-skill/v1"))
        self.assertIsNone(pattern.match("my-skill/v"))
        self.assertIsNone(pattern.match("my-skill/1"))

    @patch("subprocess.run")
    def test_run_command_success(self, mock_run):
        """Test successful command execution"""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "success"
        mock_run.return_value = mock_proc

        res = self.manager._run_command(["ls", "-la"])
        self.assertEqual(res.stdout, "success")
        self.assertEqual(res.returncode, 0)

    @patch("subprocess.run")
    def test_check_network(self, mock_run):
        """Test network check via gh api"""
        # Case 1: Success
        mock_proc_success = MagicMock()
        mock_proc_success.returncode = 0
        mock_proc_success.stdout = "user"
        mock_run.return_value = mock_proc_success
        self.assertTrue(self.manager.check_network())

        # Case 2: Failure
        mock_proc_fail = MagicMock()
        mock_proc_fail.returncode = 1
        mock_run.return_value = mock_proc_fail
        self.assertFalse(self.manager.check_network())

    def test_ignore_patterns(self):
        """Test file ignore logic"""
        ignore_list = [
            ".git",
            "__pycache__",
            "node_modules",
            ".venv",
            ".DS_Store",
            "__MACOSX",
            ".idea",
            ".vscode",
            "*.pyc",
            "*.pyo",
            "Thumbs.db",
            ".pytest_cache",
        ]

        def is_ignored(name):
            if name in ignore_list:
                return True
            if name.endswith(".pyc") or name.endswith(".pyo"):
                return True
            return False

        self.assertTrue(is_ignored(".git"))
        self.assertTrue(is_ignored(".venv"))
        self.assertTrue(is_ignored("script.pyc"))
        self.assertFalse(is_ignored("script.py"))
        self.assertFalse(is_ignored("SKILL.md"))

    def test_self_protection(self):
        """Test that self-modification is prevented"""
        # Test save protection
        with self.assertRaises(SnapshotError) as cm:
            self.manager.save("skill-snapshot")
        self.assertIn("self-modification is not allowed", str(cm.exception))

        # Test restore protection (restore calls sys.exit(1) on failure)
        with patch("sys.exit") as mock_exit:
            with patch("sys.stderr"):  # Silence error output
                self.manager.delete_snapshot("skill-snapshot", "v1")
                mock_exit.assert_called_with(1)

    @patch("pathlib.Path.iterdir")
    @patch("pathlib.Path.exists")
    def test_scan_filtering(self, mock_exists, mock_iterdir):
        """Test the scan filtering logic"""

        # Setup mock items
        def create_mock_path(name, is_dir=True, has_skill_md=True):
            p = MagicMock()
            p.name = name
            p.is_dir.return_value = is_dir
            p.is_symlink.return_value = False

            # Mock (item / "SKILL.md").exists()
            skill_md = MagicMock()
            skill_md.exists.return_value = has_skill_md
            p.__truediv__.return_value = skill_md
            return p

        # 1. Valid skill
        valid = create_mock_path("valid-skill")
        # 2. Archive (skip)
        archive = create_mock_path("archive")
        # 3. Dot folder (skip)
        dot = create_mock_path(".git")
        # 4. Self (skip)
        self_skill = create_mock_path("skill-snapshot")
        # 5. File (skip)
        file_item = create_mock_path("notes.txt", is_dir=False)
        # 6. No SKILL.md (skip)
        no_md = create_mock_path("broken-skill", has_skill_md=False)

        mock_iterdir.return_value = [valid, archive, dot, self_skill, file_item, no_md]
        mock_exists.return_value = True

        # Capture output
        from io import StringIO

        with patch("sys.stdout", new=StringIO()) as fake_out:
            with patch.object(self.manager, "_get_dir_size", return_value=100):
                self.manager.scan()
                output = fake_out.getvalue()

        # Valid skill should be listed
        self.assertIn("- valid-skill", output)
        self.assertNotIn("- archive", output)
        self.assertNotIn("- .git", output)
        self.assertIn("Found 1 skills", output)


class TestCacheSystem(unittest.TestCase):
    """测试哈希缓存系统"""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)

        self.skills_dir = self.tmp_path / "skills"
        self.skills_dir.mkdir()

        self.repo_dir = self.tmp_path / "repo"
        self.repo_dir.mkdir()
        self.cache_dir = self.repo_dir / ".snapshot_cache"

        self.patcher_skills = patch(
            "snapshot_manager.SKILLS_DIR_DEFAULT", self.skills_dir
        )
        self.patcher_repo = patch("snapshot_manager.LOCAL_REPO", self.repo_dir)
        self.patcher_cache = patch("snapshot_manager.CACHE_DIR", self.cache_dir)

        self.patcher_skills.start()
        self.patcher_repo.start()
        self.patcher_cache.start()

        self.mock_check_version = patch.object(
            SkillSnapshotManager, "_check_tool_versions"
        ).start()
        self.mock_network = patch.object(
            SkillSnapshotManager, "check_network", return_value=True
        ).start()

        self.manager = SkillSnapshotManager()
        self.manager.local_repo = self.repo_dir
        self.manager.skills_dir = self.skills_dir

    def tearDown(self):
        self.tmp_dir.cleanup()
        patch.stopall()

    def test_compute_file_hash(self):
        """测试文件哈希计算"""
        test_file = self.tmp_path / "test.txt"
        content = b"hello world"
        test_file.write_bytes(content)

        import hashlib

        expected_hash = hashlib.sha256(content).hexdigest()

        actual_hash = self.manager._compute_file_hash(test_file)
        self.assertEqual(actual_hash, expected_hash)
        self.assertEqual(
            self.manager._compute_file_hash(self.tmp_path / "nonexistent"), ""
        )

    def test_has_changes_fast_no_cache(self):
        """测试无缓存时的变更检测"""
        skill_name = "skill1"
        skill_path = self.skills_dir / skill_name
        skill_path.mkdir()
        (skill_path / "SKILL.md").write_text("content")

        self.assertTrue(self.manager._has_changes_fast(skill_name))

        snapshot_path = self.repo_dir / skill_name
        snapshot_path.mkdir()
        self.assertTrue(self.manager._has_changes_fast(skill_name))

    def test_save_cache(self):
        """测试缓存保存和读取"""
        skill_name = "skill_cache_test"
        cache_data = {"files": {"test": "data"}, "last_backup": "now"}

        self.manager._save_cache(skill_name, cache_data)

        cache_file = self.cache_dir / f"{skill_name}.json"
        self.assertTrue(cache_file.exists())

        loaded = self.manager._load_cache(skill_name)
        self.assertEqual(loaded["files"], cache_data["files"])
        self.assertEqual(loaded["cache_version"], "1.0")


class TestLockMechanism(unittest.TestCase):
    """测试并发锁机制"""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.repo_dir = Path(self.tmp_dir.name)

        self.patcher = patch("snapshot_manager.LOCAL_REPO", self.repo_dir)
        self.patcher.start()

        patch.object(SkillSnapshotManager, "_check_tool_versions").start()
        # Mock _find_skills_dir to avoid issues during init
        patch.object(
            SkillSnapshotManager, "_find_skills_dir", return_value=self.repo_dir
        ).start()

        self.manager = SkillSnapshotManager()
        self.manager.local_repo = self.repo_dir

    def tearDown(self):
        self.tmp_dir.cleanup()
        patch.stopall()

    def test_acquire_lock_success(self):
        """测试成功获取锁"""
        self.assertTrue(self.manager._acquire_lock())
        self.assertTrue((self.repo_dir / ".snapshot.lock").exists())
        self.manager._release_lock()
        self.assertFalse((self.repo_dir / ".snapshot.lock").exists())

    def test_acquire_lock_fail(self):
        """测试锁已被占用"""
        lock_file = self.repo_dir / ".snapshot.lock"
        # Ensure parent dir exists
        self.repo_dir.mkdir(parents=True, exist_ok=True)
        lock_file.write_text("pid\ntime")

        self.assertFalse(self.manager._acquire_lock())

    def test_stale_lock_cleanup(self):
        """测试过期锁清理"""
        lock_file = self.repo_dir / ".snapshot.lock"
        self.repo_dir.mkdir(parents=True, exist_ok=True)
        lock_file.write_text("pid\ntime")

        stale_time = time.time() - 660
        os.utime(str(lock_file), (stale_time, stale_time))

        self.assertTrue(self.manager._acquire_lock())


class TestVersionCheck(unittest.TestCase):
    """测试版本检查功能"""

    @patch("subprocess.run")
    def test_check_tool_versions_ok(self, mock_run):
        """测试版本满足要求"""

        def side_effect(cmd, **kwargs):
            mock_res = MagicMock()
            mock_res.returncode = 0
            if "git" in cmd and "--version" in cmd:
                mock_res.stdout = "git version 2.40.0"
            elif "gh" in cmd and "--version" in cmd:
                mock_res.stdout = "gh version 2.50.0"
            return mock_res

        mock_run.side_effect = side_effect

        manager = SkillSnapshotManager()
        manager._check_tool_versions()


class TestCoreWorkflow(unittest.TestCase):
    """关键流程集成测试"""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.skills_dir = self.root / "skills"
        self.repo_dir = self.root / "repo"
        self.skills_dir.mkdir()
        self.repo_dir.mkdir()
        (self.repo_dir / ".git").mkdir()

        self.patchers = [
            patch("snapshot_manager.SKILLS_DIR_DEFAULT", self.skills_dir),
            patch("snapshot_manager.LOCAL_REPO", self.repo_dir),
            patch("snapshot_manager.CACHE_DIR", self.repo_dir / ".snapshot_cache"),
            patch.object(SkillSnapshotManager, "_check_tool_versions"),
            patch.object(SkillSnapshotManager, "check_network", return_value=True),
        ]
        for p in self.patchers:
            p.start()

        self.manager = SkillSnapshotManager()
        self.manager.local_repo = self.repo_dir
        self.manager.skills_dir = self.skills_dir

    def tearDown(self):
        patch.stopall()
        self.tmp_dir.cleanup()

    @patch("subprocess.run")
    def test_save_flow_success(self, mock_run):
        """测试 save 成功流程"""
        skill_name = "test-skill"
        (self.skills_dir / skill_name).mkdir()
        (self.skills_dir / skill_name / "SKILL.md").write_text("v1")

        def side_effect(cmd, **kwargs):
            m = MagicMock()
            m.returncode = 0
            m.stdout = ""
            if "tag" in cmd and "-l" in cmd:
                m.stdout = ""
            if "diff" in cmd and "--cached" in cmd:
                m.returncode = 1
            return m

        mock_run.side_effect = side_effect

        with patch.object(self.manager, "_acquire_lock", return_value=True):
            res = self.manager.save(
                skill_name, "msg", sync_remote=False, skip_fast_check=True
            )

        self.assertTrue(res)
        self.assertTrue((self.repo_dir / skill_name / "SKILL.md").exists())

    @patch("subprocess.run")
    def test_save_no_changes(self, mock_run):
        """测试 save 无变更流程"""
        skill_name = "test-skill"
        (self.skills_dir / skill_name).mkdir()

        def side_effect(cmd, **kwargs):
            m = MagicMock()
            m.returncode = 0
            if "diff" in cmd and "--cached" in cmd:
                m.returncode = 0  # No changes
            return m

        mock_run.side_effect = side_effect

        with patch.object(self.manager, "_acquire_lock", return_value=True):
            res = self.manager.save(
                skill_name, "msg", sync_remote=False, skip_fast_check=True
            )

        self.assertFalse(res)

    @patch("subprocess.run")
    def test_restore_flow(self, mock_run):
        """测试 restore 流程"""
        skill_name = "test-skill"
        version = "v1"

        (self.repo_dir / skill_name).mkdir()
        (self.repo_dir / skill_name / "SKILL.md").write_text("restored")

        target_dir = self.skills_dir / skill_name

        mock_run.return_value.returncode = 0

        with patch.object(self.manager, "_acquire_lock", return_value=True):
            self.manager.restore(skill_name, version)

        self.assertTrue(target_dir.exists())
        self.assertEqual((target_dir / "SKILL.md").read_text(), "restored")


class TestBackupAll(unittest.TestCase):
    """测试批量备份功能"""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.skills_dir = self.root / "skills"
        self.repo_dir = self.root / "repo"
        self.skills_dir.mkdir()
        self.repo_dir.mkdir()

        self.patchers = [
            patch("snapshot_manager.SKILLS_DIR_DEFAULT", self.skills_dir),
            patch("snapshot_manager.LOCAL_REPO", self.repo_dir),
            patch("snapshot_manager.CACHE_DIR", self.repo_dir / ".snapshot_cache"),
            patch.object(SkillSnapshotManager, "_check_tool_versions"),
            patch.object(SkillSnapshotManager, "check_network", return_value=True),
        ]
        for p in self.patchers:
            p.start()

        self.manager = SkillSnapshotManager()
        self.manager.local_repo = self.repo_dir
        self.manager.skills_dir = self.skills_dir

    def tearDown(self):
        patch.stopall()
        self.tmp_dir.cleanup()

    @patch("subprocess.run")
    def test_backup_all_flow(self, mock_run):
        """测试 backup_all 流程"""
        (self.skills_dir / "skill1").mkdir()
        (self.skills_dir / "skill1" / "SKILL.md").write_text("s1")
        (self.skills_dir / "skill2").mkdir()
        (self.skills_dir / "skill2" / "SKILL.md").write_text("s2")

        def side_effect(cmd, **kwargs):
            m = MagicMock()
            m.returncode = 0
            if "diff" in cmd:
                pass
            return m

        mock_run.side_effect = side_effect

        def mock_has_changes(name):
            return name == "skill1"

        with patch.object(
            self.manager, "_has_changes_fast", side_effect=mock_has_changes
        ):
            with patch.object(self.manager, "_acquire_lock", return_value=True):
                with patch.object(self.manager, "save", return_value=True) as mock_save:
                    self.manager.backup_all("msg")

                    mock_save.assert_called()
                    args, _ = mock_save.call_args
                    self.assertEqual(args[0], "skill1")


if __name__ == "__main__":
    unittest.main()
