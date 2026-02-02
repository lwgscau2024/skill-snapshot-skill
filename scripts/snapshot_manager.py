"""
Skill Snapshot Manager - 技能版本快照管理工具

提供 Claude Code 技能的版本控制功能，包括：
- 初始化 Git 仓库并同步到 GitHub
- 保存/恢复技能快照
- 批量备份所有技能
- 基于哈希的增量缓存系统

Author: Claude Code
License: MIT
"""
import argparse
import os
import shutil
import subprocess
import sys
import re
import tempfile
import time
import zipfile
import difflib
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Set, Dict


# Custom Exceptions
class SnapshotError(Exception):
    """快照操作异常基类"""

    pass


class NetworkError(SnapshotError):
    """网络连接错误"""

    pass


class SkillNotFoundError(SnapshotError):
    """技能未找到"""

    pass


# Configuration
REPO_NAME = "skill-snapshots"
DEFAULT_BRANCH = "main"  # Git default branch name
LOCAL_REPO = Path.home() / ".claude" / "skill-snapshots"
SKILLS_DIR_DEFAULT = Path.home() / ".claude" / "skills"
CACHE_DIR = LOCAL_REPO / ".snapshot_cache"  # Hash cache directory
CACHE_VERSION = "1.0"  # Cache format version for compatibility

# Size limit for skills (10MB)
MAX_SKILL_SIZE_MB = 10
MAX_SKILL_SIZE_BYTES = MAX_SKILL_SIZE_MB * 1024 * 1024

# Self skill name (to prevent self-modification)
SELF_SKILL_NAME = "skill-snapshot"

# Windows Console Constants
STD_OUTPUT_HANDLE = -11  # Standard output handle for Windows console

# Enable ANSI colors on Windows 10+
if sys.platform == "win32":
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(STD_OUTPUT_HANDLE), 7)  # Enable ANSI
    except Exception:
        pass  # Ignore if it fails, colors just won't work

# Windows Console Encoding Fix
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


class SkillSnapshotManager:
    """技能快照管理器核心类。

    负责管理技能版本快照的完整生命周期，包括：
    - 仓库初始化与远程同步
    - 技能扫描与变更检测
    - 快照保存、恢复与删除
    - 基于 SHA256 哈希的增量缓存

    Attributes:
        local_repo: 本地 Git 仓库路径
        skills_dir: 技能目录路径
        git_env: Git 命令环境变量
    """

    def __init__(self):
        self.local_repo = LOCAL_REPO
        self.skills_dir = self._find_skills_dir()
        self.git_env = os.environ.copy()
        self.git_env["GIT_TERMINAL_PROMPT"] = "0"
        # Ensure gh is in path
        if not shutil.which("gh"):
            raise SnapshotError("GitHub CLI (gh) not found. Please install it.")
        if not shutil.which("git"):
            raise SnapshotError("Git not found. Please install it.")
        # Check tool versions
        self._check_tool_versions()

    def _check_tool_versions(self):
        """Check Git and GitHub CLI versions and warn if below recommended."""
        MIN_GIT_VERSION = (2, 28)
        MIN_GH_VERSION = (2, 0)

        # Check Git version
        try:
            res = subprocess.run(
                ["git", "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if res.returncode == 0:
                # Parse "git version 2.39.0.windows.2" -> (2, 39)
                match = re.search(r"git version (\d+)\.(\d+)", res.stdout)
                if match:
                    git_ver = (int(match.group(1)), int(match.group(2)))
                    if git_ver < MIN_GIT_VERSION:
                        print(
                            f"Warning: Git version {git_ver[0]}.{git_ver[1]} detected. "
                            f"Recommended: {MIN_GIT_VERSION[0]}.{MIN_GIT_VERSION[1]}+",
                            file=sys.stderr,
                        )
        except Exception:
            pass

        # Check gh version
        try:
            res = subprocess.run(
                ["gh", "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if res.returncode == 0:
                # Parse "gh version 2.40.1 (2024-01-18)" -> (2, 40)
                match = re.search(r"gh version (\d+)\.(\d+)", res.stdout)
                if match:
                    gh_ver = (int(match.group(1)), int(match.group(2)))
                    if gh_ver < MIN_GH_VERSION:
                        print(
                            f"Warning: GitHub CLI version {gh_ver[0]}.{gh_ver[1]} detected. "
                            f"Recommended: {MIN_GH_VERSION[0]}.{MIN_GH_VERSION[1]}+",
                            file=sys.stderr,
                        )
        except Exception:
            pass

    def _ensure_git_config(self):
        """Ensure Git configuration exists (user.name and user.email).
        If missing, try to auto-configure using GitHub setup.
        """
        # Check user.name
        res_name = self._run_command(["git", "config", "user.name"], cwd=self.local_repo)
        if not res_name.stdout.strip():
            # Try getting from 'gh api user'
            res_gh = self._run_command(["gh", "api", "user", "-q", ".name // .login"])
            if res_gh.returncode == 0 and res_gh.stdout.strip():
                name = res_gh.stdout.strip()
                self._run_command(["git", "config", "user.name", name], cwd=self.local_repo)

        # Check user.email
        res_email = self._run_command(["git", "config", "user.email"], cwd=self.local_repo)
        if not res_email.stdout.strip():
            # Try getting from 'gh api user' - simple fallback
            res_gh_email = self._run_command(
                ["gh", "api", "user", "-q", '.email // "noreply@github.com"']
            )
            if res_gh_email.returncode == 0:
                email = res_gh_email.stdout.strip() or "noreply@github.com"
                self._run_command(["git", "config", "user.email", email], cwd=self.local_repo)

    def _find_skills_dir(self) -> Path:
        """Find the skills directory. Checks script location first, then default path."""
        current_script = Path(__file__).resolve()
        # structure: .../skills/skill-snapshot/scripts/snapshot_manager.py
        potential_skills_dir = current_script.parent.parent.parent

        if potential_skills_dir.name == "skills" and potential_skills_dir.exists():
            return potential_skills_dir

        # Fallback to default
        if SKILLS_DIR_DEFAULT.exists():
            return SKILLS_DIR_DEFAULT

        # Last resort: use potential dir but warn user
        if potential_skills_dir.exists():
            print(f"Warning: Using skills directory: {potential_skills_dir}", file=sys.stderr)
            return potential_skills_dir

        # Create default if nothing exists
        print(
            f"Warning: Skills directory not found. Will use: {SKILLS_DIR_DEFAULT}", file=sys.stderr
        )
        return SKILLS_DIR_DEFAULT

    def _run_command(
        self,
        cmd: List[str],
        cwd: Optional[Path] = None,
        capture_output: bool = True,
        timeout: int = 300,
    ) -> subprocess.CompletedProcess:
        """Execute a command with timeout protection.

        Args:
            cmd: Command and arguments as a list
            cwd: Working directory
            capture_output: Whether to capture stdout/stderr
            timeout: Maximum seconds to wait (default 300s)

        Returns:
            CompletedProcess instance
        """
        try:
            return subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=capture_output,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=self.git_env,
                check=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            print(f"Error: Command timed out after {timeout}s: {' '.join(cmd)}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error running command {' '.join(cmd)}: {e}", file=sys.stderr)
            sys.exit(1)

    def check_network(self) -> bool:
        """Check network connectivity by verifying GitHub CLI auth status."""
        try:
            res = self._run_command(["gh", "api", "user", "-q", ".login"])
            return res.returncode == 0 and bool(res.stdout.strip())
        except Exception:
            return False

    def _ensure_main_branch(self):
        """Ensure repository is on the main branch (fix detached HEAD state)."""
        if not self.local_repo.exists():
            return
        try:
            # Check current branch
            res = self._run_command(["git", "branch", "--show-current"], cwd=self.local_repo)
            current_branch = res.stdout.strip() if res.returncode == 0 else ""

            if not current_branch:
                # Detached HEAD state - try to recover
                print("Warning: Repository in detached HEAD state, recovering...", file=sys.stderr)
                self._run_command(
                    ["git", "checkout", DEFAULT_BRANCH, "--quiet"], cwd=self.local_repo
                )
            elif current_branch != DEFAULT_BRANCH:
                # Wrong branch - switch to main
                self._run_command(
                    ["git", "checkout", DEFAULT_BRANCH, "--quiet"], cwd=self.local_repo
                )
        except Exception as e:
            print(f"Warning: Failed to ensure main branch: {e}", file=sys.stderr)

    def _acquire_lock(self) -> bool:
        """Acquire file lock to prevent concurrent operations. Returns True if acquired."""
        lock_path = self.local_repo / ".snapshot.lock"
        try:
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            # Check if lock exists and is stale (>10 minutes old)
            if lock_path.exists():
                lock_age = time.time() - lock_path.stat().st_mtime
                if lock_age > 600:  # 10 minutes
                    lock_path.unlink()  # Remove stale lock
                else:
                    return False
            # Create lock file
            lock_path.write_text(f"{os.getpid()}\n{datetime.now().isoformat()}", encoding="utf-8")
            return True
        except (OSError, PermissionError):
            return False

    def _release_lock(self):
        """Release file lock."""
        lock_path = self.local_repo / ".snapshot.lock"
        try:
            if lock_path.exists():
                lock_path.unlink()
        except (OSError, PermissionError):
            pass

    def init(self):
        """Initialize the skill snapshot repository.
        
        This involves:
        1. Checking GitHub CLI authentication and user status.
        2. Creating a private remote repository if it doesn't exist.
        3. Setting up the local Git repository and linking it to remote.
        4. Configuring .gitignore for cache files.
        """
        print("=== Skill Snapshot Initialization (Windows Optimized) ===")

        # Fix repository state if needed
        self._ensure_main_branch()

        # 1. Check GH Auth
        res = self._run_command(["gh", "auth", "status"])
        if res.returncode != 0:
            print(
                "Error: Not logged in to GitHub CLI. Please run 'gh auth login'.", file=sys.stderr
            )
            sys.exit(1)

        # Get Current User
        res_user = self._run_command(["gh", "api", "user", "-q", ".login"])
        if res_user.returncode != 0:
            print("Error: Failed to get GitHub username.", file=sys.stderr)
            sys.exit(1)
        github_user = res_user.stdout.strip()
        print(f"GitHub User: {github_user}")

        repo_full_name = f"{github_user}/{REPO_NAME}"

        # 2. Check/Create Remote Repo
        print(f"Checking remote repository: {repo_full_name}...")
        res_view = self._run_command(["gh", "repo", "view", repo_full_name])

        repo_exists = res_view.returncode == 0
        if not repo_exists:
            print(f"Creating private repository {REPO_NAME}...")
            res_create = self._run_command(
                [
                    "gh",
                    "repo",
                    "create",
                    REPO_NAME,
                    "--private",
                    "--description",
                    "Claude Code Skills Snapshots (Private Backup)",
                    "--clone=false",
                ]
            )
            if res_create.returncode != 0:
                print(f"Error creating repository: {res_create.stderr}", file=sys.stderr)
                sys.exit(1)
            print("Repository created.")
        else:
            print("Repository exists.")

        # 3. Setup Local Repo
        if not self.local_repo.exists():
            self.local_repo.mkdir(parents=True, exist_ok=True)

        # Ensure git identity is configured if repo exists or will be created
        if (self.local_repo / ".git").exists():
            self._ensure_git_config()

        # Init or Clone
        if (self.local_repo / ".git").exists():
            print(f"Local repository exists at {self.local_repo}")
            # Try to pull
            print("Syncing with remote...")
            self._run_command(
                ["git", "pull", "--quiet", "origin", DEFAULT_BRANCH], cwd=self.local_repo
            )
        else:
            # Check if remote is empty
            res_empty = self._run_command(
                ["gh", "repo", "view", repo_full_name, "--json", "isEmpty", "-q", ".isEmpty"]
            )
            is_empty = res_empty.stdout.strip() == "true"

            if is_empty:
                print("Initializing new repository...")
                self._run_command(["git", "init", "--quiet"], cwd=self.local_repo)
                self._run_command(
                    ["git", "remote", "add", "origin", f"https://github.com/{repo_full_name}.git"],
                    cwd=self.local_repo,
                )

                # Create README
                readme_content = f"# Skill Snapshots\n\nPrivate backup for Claude Code skills.\nmanaged by skill-snapshot.\n"
                (self.local_repo / "README.md").write_text(readme_content, encoding="utf-8")

                self._run_command(["git", "add", "README.md"], cwd=self.local_repo)
                self._run_command(
                    ["git", "commit", "--quiet", "-m", "Initial commit"], cwd=self.local_repo
                )
                self._run_command(["git", "branch", "-M", DEFAULT_BRANCH], cwd=self.local_repo)
                self._run_command(
                    ["git", "push", "--quiet", "-u", "origin", DEFAULT_BRANCH], cwd=self.local_repo
                )
                print("Repository initialized and pushed.")
            else:
                print(f"Cloning from {repo_full_name}...")
                # git clone requires empty or non-existent directory
                if any(self.local_repo.iterdir()):
                    # Directory is not empty, need to clean it first
                    shutil.rmtree(self.local_repo)
                elif self.local_repo.exists():
                    self.local_repo.rmdir()

                res_clone = self._run_command(
                    [
                        "git",
                        "clone",
                        "--quiet",
                        f"https://github.com/{repo_full_name}.git",
                        str(self.local_repo),
                    ]
                )
                if res_clone.returncode != 0:
                    print(f"Error cloning repository: {res_clone.stderr}", file=sys.stderr)
                    sys.exit(1)
                print("Cloned successfully.")

        # Add cache directory to .gitignore
        gitignore_path = self.local_repo / ".gitignore"
        cache_ignore_entry = ".snapshot_cache/"

        try:
            if gitignore_path.exists():
                content = gitignore_path.read_text(encoding="utf-8")
                if cache_ignore_entry not in content:
                    # Append to existing .gitignore
                    with open(gitignore_path, "a", encoding="utf-8") as f:
                        f.write(
                            f"\n# Skill snapshot cache (auto-generated)\n{cache_ignore_entry}\n"
                        )
            else:
                # Create new .gitignore
                gitignore_path.write_text(
                    f"# Skill snapshot cache (auto-generated)\n{cache_ignore_entry}\n",
                    encoding="utf-8",
                )
        except (OSError, PermissionError) as e:
            print(f"Warning: Failed to update .gitignore: {e}", file=sys.stderr)

        print("Initialization complete.")

    def _get_dir_size(self, path: Path) -> int:
        """Calculate total size of a directory in bytes."""
        total = 0
        try:
            for p in path.rglob("*"):
                if p.is_file():
                    try:
                        total += p.stat().st_size
                    except (OSError, PermissionError):
                        pass
        except (OSError, PermissionError):
            pass
        return total

    # === Hash Cache System ===

    def _get_cache_path(self, skill_name: str) -> Path:
        """Get the cache file path for a skill."""
        return CACHE_DIR / f"{skill_name}.json"

    def _load_cache(self, skill_name: str) -> Dict:
        """Load cache data for a skill. Returns empty dict if not found or version mismatch."""
        cache_path = self._get_cache_path(skill_name)
        if not cache_path.exists():
            return {}
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Check cache version compatibility
            if data.get("cache_version") != CACHE_VERSION:
                return {}  # Version mismatch, treat as empty
            return data
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_cache(self, skill_name: str, cache_data: Dict):
        """Save cache data for a skill with version information."""
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path = self._get_cache_path(skill_name)
        # Add cache version
        cache_data["cache_version"] = CACHE_VERSION
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
        except OSError as e:
            print(f"Warning: Failed to save cache: {e}", file=sys.stderr)

    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of a file."""
        hasher = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                while chunk := f.read(8192):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except (OSError, PermissionError):
            return ""

    def _get_skill_files(self, skill_path: Path) -> List[Path]:
        """Get all files in a skill directory, respecting ignore patterns."""
        files = []
        ignore_names = {
            ".git",
            "__pycache__",
            "node_modules",
            ".venv",
            ".DS_Store",
            "__MACOSX",
            ".idea",
            ".vscode",
            ".pytest_cache",
            "Thumbs.db",
        }

        for file_path in skill_path.rglob("*"):
            if not file_path.is_file():
                continue

            # Check ignore patterns
            parts = file_path.parts
            if any(part in ignore_names for part in parts):
                continue

            # Skip compiled Python files
            if file_path.suffix in (".pyc", ".pyo"):
                continue

            files.append(file_path)

        return files

    def _compute_skill_hash_incremental(self, skill_path: Path, cache_data: Dict) -> Dict:
        """Incrementally compute skill file hashes, reusing cached values where possible."""
        new_hash_data = {}
        cached_files = cache_data.get("files", {})

        for file_path in self._get_skill_files(skill_path):
            # Use forward slashes for cache keys (cross-platform compatibility)
            rel_path = str(file_path.relative_to(skill_path)).replace("\\", "/")

            try:
                stat = file_path.stat()
                cached = cached_files.get(rel_path, {})

                # Check if we can reuse cached hash
                if cached.get("mtime") == stat.st_mtime and cached.get("size") == stat.st_size:
                    # Reuse cached hash
                    new_hash_data[rel_path] = cached
                else:
                    # Recompute hash
                    file_hash = self._compute_file_hash(file_path)
                    new_hash_data[rel_path] = {
                        "hash": file_hash,
                        "mtime": stat.st_mtime,
                        "size": stat.st_size,
                    }
            except (OSError, PermissionError):
                continue

        return new_hash_data

    def _has_changes_fast(self, skill_name: str) -> bool:
        """Fast check if a skill has changes compared to cached snapshot.

        Returns:
            True if changes detected or cache miss, False if definitely no changes
        """
        skill_path = self.skills_dir / skill_name
        snapshot_path = self.local_repo / skill_name

        # If no snapshot exists, definitely needs backup
        if not snapshot_path.exists():
            return True

        # Load cache
        cache_data = self._load_cache(skill_name)
        if not cache_data or "files" not in cache_data:
            # No cache, assume changes
            return True

        # Compute current hash incrementally
        current_hashes = self._compute_skill_hash_incremental(skill_path, cache_data)
        cached_hashes = cache_data.get("files", {})

        # Quick check: different file count
        if len(current_hashes) != len(cached_hashes):
            return True

        # Check for file additions/deletions
        current_files = set(current_hashes.keys())
        cached_files = set(cached_hashes.keys())
        if current_files != cached_files:
            return True

        # Compare hashes
        for rel_path, file_info in current_hashes.items():
            cached_info = cached_hashes.get(rel_path, {})
            if file_info.get("hash") != cached_info.get("hash"):
                return True

        # No changes detected
        return False

    def _update_cache_after_save(self, skill_name: str):
        """Update cache after successfully saving a snapshot."""
        skill_path = self.skills_dir / skill_name

        # Compute fresh hashes
        current_hashes = self._compute_skill_hash_incremental(skill_path, {})

        # Save cache
        cache_data = {"last_backup": datetime.now().isoformat(), "files": current_hashes}
        self._save_cache(skill_name, cache_data)

    # === End Hash Cache System ===

    def scan(self):
        """Scan the skills directory and list available skills.
        
        Filters out:
        - Hidden directories (starting with .)
        - 'archive' directory
        - Symbolic links
        - Directories without SKILL.md
        - The skill-snapshot tool itself (self-protection)
        - Skills larger than MAX_SKILL_SIZE_MB
        """
        print("=== Scanning Skills ===")
        print(f"Skills Directory: {self.skills_dir}")

        if not self.skills_dir.exists():
            print("Skills directory not found.", file=sys.stderr)
            return

        skills = []
        skipped = []
        for item in self.skills_dir.iterdir():
            if item.is_dir():
                # Skip rules
                if item.name.startswith("."):
                    continue
                if item.name == "archive":
                    continue
                if item.is_symlink():
                    continue  # Python is_symlink handles Windows reparse points correctly usually
                if not (item / "SKILL.md").exists():
                    continue

                # Skip self (skill-snapshot)
                if item.name == SELF_SKILL_NAME:
                    skipped.append((item.name, "self"))
                    continue

                # Skip large skills (>10MB)
                size = self._get_dir_size(item)
                if size > MAX_SKILL_SIZE_BYTES:
                    skipped.append((item.name, f"size>{MAX_SKILL_SIZE_MB}MB"))
                    continue

                skills.append(item.name)

        skills.sort()
        for skill in skills:
            print(f"- {skill}")

        print(f"\nFound {len(skills)} skills.")

        if skipped:
            print(f"\nSkipped {len(skipped)} skills:")
            for name, reason in skipped:
                print(f"  - {name} ({reason})")

    def save(
        self,
        skill_name: str,
        message: Optional[str] = None,
        sync_remote: bool = True,
        skip_fast_check: bool = False,
    ) -> bool:
        """Save a skill snapshot. Returns True if snapshot was created, False if no changes.

        Args:
            skill_name: Name of the skill to save
            message: Optional commit message
            sync_remote: Whether to sync with remote before saving
            skip_fast_check: Skip fast change detection (useful for forcing save)
        """
        # Self-protection: prevent saving skill-snapshot itself
        if skill_name == SELF_SKILL_NAME:
            raise SnapshotError(
                f"Cannot save '{SELF_SKILL_NAME}' - self-modification is not allowed."
            )

        # Acquire lock to prevent concurrent operations
        if not self._acquire_lock():
            raise SnapshotError("Another snapshot operation is in progress. Please wait.")

        try:
            return self._save_impl(skill_name, message, sync_remote, skip_fast_check)
        finally:
            self._release_lock()

    def _save_impl(
        self, skill_name: str, message: Optional[str], sync_remote: bool, skip_fast_check: bool
    ) -> bool:
        """Internal implementation of save."""
        skill_path = self.skills_dir / skill_name
        if not skill_path.exists():
            raise SkillNotFoundError(f"Skill '{skill_name}' not found at {skill_path}")

        if not (self.local_repo / ".git").exists():
            raise SnapshotError("Snapshot repository not initialized. Run 'init' first.")

        if sync_remote:
            # Check network connectivity
            if not self.check_network():
                raise NetworkError("No network connectivity. Cannot push to remote.")

            # Sync remote
            print("Syncing with remote...")
            self._run_command(
                ["git", "pull", "--quiet", "origin", DEFAULT_BRANCH], cwd=self.local_repo
            )
            self._run_command(["git", "fetch", "--tags", "--quiet"], cwd=self.local_repo)

        # === OPTIMIZATION: Fast change detection ===
        if not skip_fast_check:
            if not self._has_changes_fast(skill_name):
                print(f"✓ No changes detected (fast check)")
                return False

        # Determine next version
        # List tags for this skill
        res_tags = self._run_command(["git", "tag", "-l", f"{skill_name}/v*"], cwd=self.local_repo)
        existing_tags = res_tags.stdout.strip().splitlines()

        max_ver = 0
        pattern = re.compile(rf"^{re.escape(skill_name)}/v(\d+)$")
        for tag in existing_tags:
            match = pattern.match(tag)
            if match:
                ver = int(match.group(1))
                if ver > max_ver:
                    max_ver = ver

        next_ver = max_ver + 1
        version_tag = f"v{next_ver}"
        full_tag = f"{skill_name}/{version_tag}"

        if not message:
            message = f"Snapshot at {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        print(f"=== Saving Snapshot for {skill_name} ===")
        print(f"Version: {version_tag}")
        print(f"Message: {message}")

        # Target dir in repo
        target_dir = self.local_repo / skill_name

        # Clean target if exists
        if target_dir.exists():
            shutil.rmtree(target_dir)  # robust removal

        # Copy files
        # ignore function for shutil.copytree
        def ignore_patterns(path, names):
            ignored = []
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
            for name in names:
                if name in ignore_list:
                    ignored.append(name)
                elif name.endswith(".pyc") or name.endswith(".pyo"):
                    ignored.append(name)
            return ignored

        shutil.copytree(skill_path, target_dir, ignore=ignore_patterns, dirs_exist_ok=True)

        # Git Commit
        self._run_command(["git", "add", f"{skill_name}/"], cwd=self.local_repo)

        # Check diff
        res_diff = self._run_command(["git", "diff", "--cached", "--quiet"], cwd=self.local_repo)
        if res_diff.returncode == 0:
            print("No changes detected since last snapshot.")
            # Update cache even if no snapshot was created (to avoid re-checking next time)
            self._update_cache_after_save(skill_name)
            return False  # No snapshot created

        commit_msg = f"[{skill_name}] {version_tag}: {message}"
        res_commit = self._run_command(
            ["git", "commit", "--quiet", "-m", commit_msg], cwd=self.local_repo
        )
        if res_commit.returncode != 0:
            raise SnapshotError("Error committing changes.")

        self._run_command(["git", "tag", "-a", full_tag, "-m", message], cwd=self.local_repo)

        print("Pushing to remote...")
        self._run_command(["git", "push", "--quiet", "origin", DEFAULT_BRANCH], cwd=self.local_repo)
        self._run_command(["git", "push", "--quiet", "origin", full_tag], cwd=self.local_repo)

        print(f"Snapshot saved: {full_tag}")

        # === OPTIMIZATION: Update cache after successful save ===
        self._update_cache_after_save(skill_name)

        return True  # Snapshot created successfully

    def list_snapshots(self, skill_name: Optional[str] = None):
        if not (self.local_repo / ".git").exists():
            print("Error: Snapshot repository not initialized.", file=sys.stderr)
            sys.exit(1)

        self._run_command(["git", "fetch", "--tags", "--quiet"], cwd=self.local_repo)

        search_pattern = f"*/v*" if not skill_name else f"{skill_name}/v*"

        # Use git tag -l -n1 to get tag message
        res = self._run_command(
            ["git", "tag", "-l", "-n1", search_pattern, "--sort=-creatordate"], cwd=self.local_repo
        )

        if not res.stdout.strip():
            print("No snapshots found.")
            return

        print(f"{'SNAPSHOT':<30} | {'MESSAGE'}")
        print("-" * 60)
        for line in res.stdout.splitlines():
            parts = line.split(maxsplit=1)
            if len(parts) >= 2:
                tag = parts[0]
                msg = parts[1]
                print(f"{tag:<30} | {msg}")
            else:
                print(line)

    def restore(self, skill_name: str, version: Optional[str] = None):
        # Self-protection: prevent restoring skill-snapshot itself
        if skill_name == SELF_SKILL_NAME:
            print(
                f"Error: Cannot restore '{SELF_SKILL_NAME}' - self-modification is not allowed.",
                file=sys.stderr,
            )
            print(
                "Restoring this skill would delete the currently running script.", file=sys.stderr
            )
            sys.exit(1)

        # Implementation of restore logic
        if not version:
            print(f"Listing versions for {skill_name}...")
            self.list_snapshots(skill_name)
            print(f"\nUsage: restore {skill_name} <version>")
            return

        # Acquire lock to prevent concurrent operations
        if not self._acquire_lock():
            print("Error: Another snapshot operation is in progress. Please wait.", file=sys.stderr)
            sys.exit(1)

        try:
            self._restore_impl(skill_name, version)
        finally:
            self._release_lock()

    def _restore_impl(self, skill_name: str, version: str):
        """Internal implementation of restore."""
        # Check network connectivity
        if not self.check_network():
            print("Error: No network connectivity. Cannot sync with remote.", file=sys.stderr)
            sys.exit(1)

        # Handle "v1" vs "skill/v1"
        if not version.startswith(f"{skill_name}/"):
            full_tag = f"{skill_name}/{version}"
        else:
            full_tag = version

        print(f"Restoring {full_tag}...")

        try:
            # 1. Update repo to main
            self._run_command(["git", "checkout", DEFAULT_BRANCH, "--quiet"], cwd=self.local_repo)
            self._run_command(["git", "pull", "--quiet"], cwd=self.local_repo)

            # 2. Check if tag exists
            res_check = self._run_command(["git", "rev-parse", full_tag], cwd=self.local_repo)
            if res_check.returncode != 0:
                print(f"Error: Version {full_tag} not found.", file=sys.stderr)
                sys.exit(1)

            # 3. Checkout the specific folder from that tag
            self._run_command(["git", "checkout", full_tag, "--quiet"], cwd=self.local_repo)

            source = self.local_repo / skill_name
            dest = self.skills_dir / skill_name

            if not source.exists():
                print(f"Error: Skill content not found in snapshot {full_tag}.", file=sys.stderr)
                sys.exit(1)

            print(f"Restoring to {dest}...")

            # Backup-Swap Strategy for Safe Restore
            backup_path = None
            if dest.exists():
                backup_path = dest.with_suffix(f".bak.{int(time.time())}")
                try:
                    shutil.move(str(dest), str(backup_path))
                    print(f"Backed up current version to {backup_path.name}")
                except Exception as e:
                    print(f"Error creating backup: {e}", file=sys.stderr)
                    sys.exit(1)

            # Restore
            try:
                shutil.copytree(source, dest, dirs_exist_ok=True)
            except Exception as e:
                # Rollback if restore fails
                print(f"Restore failed ({e}), reverting...", file=sys.stderr)
                if dest.exists():
                    shutil.rmtree(dest)
                if backup_path and backup_path.exists():
                    shutil.move(str(backup_path), str(dest))
                    print("Reverted to previous version.")
                raise e

            # Cleanup backup if successful
            if backup_path and backup_path.exists():
                try:
                    shutil.rmtree(backup_path)
                except Exception as e:
                    print(f"Warning: Failed to remove backup {backup_path}: {e}", file=sys.stderr)

            print(f"Successfully restored {skill_name} to {version}")

        finally:
            # Revert repo to main
            self._run_command(["git", "checkout", DEFAULT_BRANCH, "--quiet"], cwd=self.local_repo)

    def delete_snapshot(self, skill_name: str, version: str):
        # Self-protection: prevent deleting skill-snapshot snapshots
        if skill_name == SELF_SKILL_NAME:
            print(
                f"Error: Cannot delete snapshots of '{SELF_SKILL_NAME}' - self-modification is not allowed.",
                file=sys.stderr,
            )
            sys.exit(1)

        # Acquire lock to prevent concurrent operations
        if not self._acquire_lock():
            print("Error: Another snapshot operation is in progress. Please wait.", file=sys.stderr)
            sys.exit(1)

        try:
            self._delete_snapshot_impl(skill_name, version)
        finally:
            self._release_lock()

    def _delete_snapshot_impl(self, skill_name: str, version: str):
        """Internal implementation of delete_snapshot."""
        # Check network connectivity
        if not self.check_network():
            print("Error: No network connectivity. Cannot delete remote tag.", file=sys.stderr)
            sys.exit(1)

        # Ensure version string implies full tag format correctly
        if version.startswith(f"{skill_name}/"):
            full_tag = version
        elif "/" in version:
            # User might have passed "other_skill/v1" while trying to delete for "skill_name"
            # This is a dangerous mismatch, fail immediately.
            print(
                f"Error: Version '{version}' does not belong to skill '{skill_name}'.",
                file=sys.stderr,
            )
            sys.exit(1)
        else:
            full_tag = f"{skill_name}/{version}"

        print(f"Deleting snapshot {full_tag}...")

        # Verify tag existence before attempting delete
        res_check = self._run_command(["git", "rev-parse", full_tag], cwd=self.local_repo)
        if res_check.returncode != 0:
            print(f"Error: Version {full_tag} not found.", file=sys.stderr)
            sys.exit(1)

        # Delete local tag
        res = self._run_command(["git", "tag", "-d", full_tag], cwd=self.local_repo)
        if res.returncode != 0:
            print("Error deleting local tag.", file=sys.stderr)
            sys.exit(1)

        # Delete remote tag
        print("Deleting remote tag...")
        res_remote = self._run_command(
            ["git", "push", "origin", "--delete", full_tag], cwd=self.local_repo
        )
        if res_remote.returncode != 0:
            print("Error deleting remote tag (might verify manually).", file=sys.stderr)

        print("Done.")

    def backup_all(self, message: Optional[str] = None):
        """Backup all skills that have changes.
        
        Features:
        - Fast change detection using hash cache to skip unchanged skills.
        - Concurrent operation protection using file lock.
        - One-time remote sync to improve performance.
        - Summarizes results (scanned, changed, backed up).
        
        Args:
            message: Optional commit message for the snapshots.
        """
        print("=== Backing Up All Skills ===")

        # Acquire lock to prevent concurrent operations
        if not self._acquire_lock():
            print("Error: Another snapshot operation is in progress. Please wait.", file=sys.stderr)
            sys.exit(1)

        try:
            # Check network connectivity ONCE
            if not self.check_network():
                print("Error: No network connectivity. Cannot push to remote.", file=sys.stderr)
                sys.exit(1)

            if not self.skills_dir.exists():
                print("Skills directory not found.", file=sys.stderr)
                return

            # Sync remote ONCE
            print("Syncing with remote...")
            if (self.local_repo / ".git").exists():
                self._run_command(
                    ["git", "pull", "--quiet", "origin", DEFAULT_BRANCH], cwd=self.local_repo
                )
                self._run_command(["git", "fetch", "--tags", "--quiet"], cwd=self.local_repo)

            # Scan for skills
            skills = []
            for item in self.skills_dir.iterdir():
                if item.is_dir():
                    if item.name.startswith("."):
                        continue
                    if item.name == "archive":
                        continue
                    if item.is_symlink():
                        continue
                    if not (item / "SKILL.md").exists():
                        continue
                    if item.name == SELF_SKILL_NAME:
                        continue
                    skills.append(item.name)

            if not skills:
                print("No skills found to backup.")
                return

            print(f"Found {len(skills)} skills to backup.")

            # === OPTIMIZATION: Pre-scan for changes ===
            print("\nScanning for changes...")
            skills_to_backup = []
            unchanged_skills = []

            for skill in skills:
                if self._has_changes_fast(skill):
                    skills_to_backup.append(skill)
                    print(f"  ✓ {skill}: Changes detected")
                else:
                    unchanged_skills.append(skill)
                    print(f"  - {skill}: No changes")

            # Show summary
            if not skills_to_backup:
                print("\n✓ All skills are up-to-date. No backup needed.")
                return

            print(f"\n{len(skills_to_backup)} skill(s) with changes:")
            for skill in skills_to_backup:
                print(f"  • {skill}")

            if unchanged_skills:
                print(f"\n{len(unchanged_skills)} skill(s) unchanged (skipped):")
                for skill in unchanged_skills[:5]:  # Show first 5
                    print(f"  • {skill}")
                if len(unchanged_skills) > 5:
                    print(f"  ... and {len(unchanged_skills) - 5} more")

            # Backup modified skills
            print(f"\n=== Backing up {len(skills_to_backup)} modified skills ===")

            success_count = 0
            for i, skill in enumerate(skills_to_backup, 1):
                print(f"\n[{i}/{len(skills_to_backup)}] Processing {skill}...")
                try:
                    # Pass sync_remote=False to avoid redundant checks
                    created = self.save(skill, message, sync_remote=False, skip_fast_check=True)
                    if created:
                        success_count += 1
                except SnapshotError as e:
                    print(f"Failed to backup {skill}: {e}")
                except Exception as e:
                    print(f"Error backing up {skill}: {e}")

            # Final summary
            print(f"\n{'='*60}")
            print(f"Backup complete!")
            print(f"")
            print(f"Results:")
            print(f"  - Scanned: {len(skills)} skills")
            print(f"  - Had changes: {len(skills_to_backup)} skills")
            print(f"  - Successfully backed up: {success_count}/{len(skills_to_backup)} skills")
            if unchanged_skills:
                print(f"  - Unchanged (skipped): {len(unchanged_skills)} skills")
        finally:
            self._release_lock()

    def diff(self, skill_name: str, version: Optional[str] = None):
        """Compare current skill files with a snapshot version."""
        if not (self.local_repo / ".git").exists():
            print("Error: Snapshot repository not initialized.", file=sys.stderr)
            sys.exit(1)

        skill_path = self.skills_dir / skill_name
        if not skill_path.exists():
            print(f"Error: Skill '{skill_name}' not found at {skill_path}", file=sys.stderr)
            sys.exit(1)

        # Fetch tags
        self._run_command(["git", "fetch", "--tags", "--quiet"], cwd=self.local_repo)

        # Resolve version
        if not version:
            res = self._run_command(["git", "tag", "-l", f"{skill_name}/v*"], cwd=self.local_repo)
            tags = res.stdout.strip().splitlines()
            if not tags:
                print(f"No snapshots found for {skill_name}")
                return

            # Sort tags structure skill/vN
            def ver_key(t: str) -> int:
                try:
                    return int(t.split("/v")[1])
                except (ValueError, IndexError):
                    return 0

            tags.sort(key=ver_key)
            full_tag = tags[-1]
            version = full_tag.split("/")[-1]
            print(f"Using latest version: {version}")
        else:
            if not version.startswith(f"{skill_name}/"):
                full_tag = f"{skill_name}/{version}"
            else:
                full_tag = version

        # Verify tag exists
        res_check = self._run_command(["git", "rev-parse", full_tag], cwd=self.local_repo)
        if res_check.returncode != 0:
            print(f"Error: Version {full_tag} not found.", file=sys.stderr)
            sys.exit(1)

        print(f"=== Diff: Local vs {full_tag} ===")

        # Create temp dir
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            zip_path = temp_path / "snapshot.zip"

            # git archive to zip
            res_arch = self._run_command(
                [
                    "git",
                    "archive",
                    "--format=zip",
                    f"--output={zip_path}",
                    full_tag,
                    f"{skill_name}/",
                ],
                cwd=self.local_repo,
            )

            if res_arch.returncode != 0:
                print(f"Error retrieving snapshot: {res_arch.stderr}", file=sys.stderr)
                return

            # Verify zip file exists and has content
            if not zip_path.exists() or zip_path.stat().st_size == 0:
                print("Error: Failed to create snapshot archive.", file=sys.stderr)
                return

            # Extract
            try:
                with zipfile.ZipFile(zip_path, "r") as zip_ref:
                    zip_ref.extractall(temp_path)
            except zipfile.BadZipFile:
                print("Error: Corrupted snapshot archive.", file=sys.stderr)
                return

            snapshot_skill_path = temp_path / skill_name

            # Compare
            self._compare_dirs(snapshot_skill_path, skill_path)

    def _compare_dirs(self, dir1: Path, dir2: Path):
        """Compare two directories and show differences.

        Args:
            dir1: Snapshot directory
            dir2: Local directory
        """

        # Get all files relative
        def get_files(d: Path) -> Set[Path]:
            files = set()
            if not d.exists():
                return files
            for p in d.rglob("*"):
                if p.is_file():
                    # Check ignores
                    parts = p.parts
                    ignore_names = {
                        ".git",
                        "__pycache__",
                        "node_modules",
                        ".venv",
                        ".DS_Store",
                        "__MACOSX",
                        ".idea",
                        ".vscode",
                        ".pytest_cache",
                        "Thumbs.db",
                    }
                    if any(part in ignore_names for part in parts):
                        continue
                    # Skip compiled Python files
                    if p.suffix in (".pyc", ".pyo"):
                        continue
                    files.add(p.relative_to(d))
            return files

        files1 = get_files(dir1)
        files2 = get_files(dir2)

        all_files = sorted(list(files1.union(files2)))

        has_diff = False

        for f in all_files:
            p1 = dir1 / f
            p2 = dir2 / f

            if f in files1 and f not in files2:
                print(f"[-] Removed: {f}")
                has_diff = True
            elif f not in files1 and f in files2:
                print(f"[+] Added: {f}")
                has_diff = True
            else:
                # Compare content
                try:
                    c1 = p1.read_text(encoding="utf-8", errors="replace").splitlines()
                    c2 = p2.read_text(encoding="utf-8", errors="replace").splitlines()

                    diff_lines = list(
                        difflib.unified_diff(
                            c1, c2, fromfile=f"Snapshot/{f}", tofile=f"Local/{f}", lineterm=""
                        )
                    )

                    if diff_lines:
                        print(f"[~] Modified: {f}")
                        for line in diff_lines[:20]:  # Show first 20 lines of diff
                            color = ""
                            if line.startswith("+"):
                                color = "\033[92m"  # Green
                            elif line.startswith("-"):
                                color = "\033[91m"  # Red
                            elif line.startswith("@"):
                                color = "\033[96m"  # Cyan
                            print(f"{color}{line}\033[0m")
                        if len(diff_lines) > 20:
                            print(f"... and {len(diff_lines)-20} more lines.")
                        has_diff = True
                except Exception as e:
                    print(f"[!] Error comparing {f}: {e}")

        if not has_diff:
            print("✓ No differences found.")

    # === Cache Maintenance Commands ===

    def rebuild_cache(self, skill_name: Optional[str] = None):
        """Rebuild hash cache for one or all skills."""
        if skill_name:
            # Rebuild cache for specific skill
            skill_path = self.skills_dir / skill_name
            if not skill_path.exists():
                print(f"Error: Skill '{skill_name}' not found.", file=sys.stderr)
                sys.exit(1)

            print(f"Rebuilding cache for {skill_name}...")
            self._update_cache_after_save(skill_name)
            print("✓ Cache rebuilt successfully.")
        else:
            # Rebuild cache for all skills
            print("Rebuilding cache for all skills...")

            skills = []
            for item in self.skills_dir.iterdir():
                if item.is_dir():
                    if item.name.startswith("."):
                        continue
                    if item.name == "archive":
                        continue
                    if item.is_symlink():
                        continue
                    if not (item / "SKILL.md").exists():
                        continue
                    if item.name == SELF_SKILL_NAME:
                        continue
                    skills.append(item.name)

            for skill in skills:
                print(f"  - {skill}")
                self._update_cache_after_save(skill)

            print(f"\n✓ Rebuilt cache for {len(skills)} skills.")

    def clear_cache(self, skill_name: Optional[str] = None):
        """Clear hash cache for one or all skills."""
        if skill_name:
            # Clear cache for specific skill
            cache_path = self._get_cache_path(skill_name)
            if cache_path.exists():
                cache_path.unlink()
                print(f"✓ Cleared cache for {skill_name}")
            else:
                print(f"No cache found for {skill_name}")
        else:
            # Clear all cache
            if CACHE_DIR.exists():
                shutil.rmtree(CACHE_DIR)
                print("✓ Cleared all cache files.")
            else:
                print("No cache directory found.")

    def status(self):
        """Show status of all skills: changes, cache, and repository state."""
        print("=== Skill Snapshot Status ===\n")

        # 1. Repository status
        print("📁 Repository Status:")
        if (self.local_repo / ".git").exists():
            # Check branch
            res = self._run_command(["git", "branch", "--show-current"], cwd=self.local_repo)
            current_branch = res.stdout.strip() if res.returncode == 0 else "unknown"
            print(f"  - Branch: {current_branch}")

            # Check if there are uncommitted changes
            res_status = self._run_command(["git", "status", "--porcelain"], cwd=self.local_repo)
            if res_status.stdout.strip():
                print(f"  - Local changes: Yes (uncommitted)")
            else:
                print(f"  - Local changes: None")
        else:
            print("  - Not initialized (run 'init' first)")

        # 2. Cache status
        print("\n📦 Cache Status:")
        if CACHE_DIR.exists():
            cache_files = list(CACHE_DIR.glob("*.json"))
            print(f"  - Location: {CACHE_DIR}")
            print(f"  - Cached skills: {len(cache_files)}")
            print(f"  - Cache version: {CACHE_VERSION}")
        else:
            print("  - No cache found")

        # 3. Skills change status
        print("\n🔍 Skills Change Detection:")
        if not self.skills_dir.exists():
            print("  - Skills directory not found")
            return

        skills = []
        for item in self.skills_dir.iterdir():
            if item.is_dir():
                if item.name.startswith("."):
                    continue
                if item.name == "archive":
                    continue
                if item.is_symlink():
                    continue
                if not (item / "SKILL.md").exists():
                    continue
                if item.name == SELF_SKILL_NAME:
                    continue
                skills.append(item.name)

        skills.sort()
        changed = []
        unchanged = []

        for skill in skills:
            if self._has_changes_fast(skill):
                changed.append(skill)
            else:
                unchanged.append(skill)

        print(f"  - Total skills: {len(skills)}")
        print(f"  - Changed: {len(changed)}")
        print(f"  - Unchanged: {len(unchanged)}")

        if changed:
            print(f"\n⚠️  Skills with changes:")
            for skill in changed:
                print(f"    • {skill}")
        else:
            print(f"\n✅ All skills are up-to-date!")


def main():
    parser = argparse.ArgumentParser(description="Skill Snapshot Manager")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    subparsers.add_parser("init", help="Initialize snapshot repository")
    subparsers.add_parser("scan", help="Scan for available skills")

    save_parser = subparsers.add_parser("save", help="Save a skill snapshot")
    save_parser.add_argument("skill_name", help="Name of the skill")
    save_parser.add_argument("message", nargs="?", help="Snapshot message")

    list_parser = subparsers.add_parser("list", help="List snapshots")
    list_parser.add_argument("skill_name", nargs="?", help="Filter by skill name")

    list_all_parser = subparsers.add_parser("list-all", help="List all snapshots")

    restore_parser = subparsers.add_parser("restore", help="Restore a skill snapshot")
    restore_parser.add_argument("skill_name", help="Name of the skill")
    restore_parser.add_argument("version", nargs="?", help="Version tag (e.g., v1)")

    del_parser = subparsers.add_parser("delete", help="Delete a snapshot")
    del_parser.add_argument("skill_name", help="Name of the skill")
    del_parser.add_argument("version", help="Version tag to delete")

    backup_all_parser = subparsers.add_parser("backup-all", help="Backup all skills")
    backup_all_parser.add_argument("message", nargs="?", help="Snapshot message")

    diff_parser = subparsers.add_parser("diff", help="Diff skill against snapshot")
    diff_parser.add_argument("skill_name", help="Name of the skill")
    diff_parser.add_argument("version", nargs="?", help="Version tag (e.g., v1)")

    # Cache maintenance commands
    rebuild_cache_parser = subparsers.add_parser("rebuild-cache", help="Rebuild hash cache")
    rebuild_cache_parser.add_argument(
        "skill_name", nargs="?", help="Skill name (optional, rebuilds all if omitted)"
    )

    clear_cache_parser = subparsers.add_parser("clear-cache", help="Clear hash cache")
    clear_cache_parser.add_argument(
        "skill_name", nargs="?", help="Skill name (optional, clears all if omitted)"
    )

    # Status command
    subparsers.add_parser("status", help="Show snapshot status for all skills")

    args = parser.parse_args()

    manager = SkillSnapshotManager()

    if args.command == "init":
        manager.init()
    elif args.command == "scan":
        manager.scan()
    elif args.command == "save":
        manager.save(args.skill_name, args.message)
    elif args.command == "list":
        manager.list_snapshots(args.skill_name)
    elif args.command == "list-all":
        manager.list_snapshots(None)
    elif args.command == "restore":
        manager.restore(args.skill_name, args.version)
    elif args.command == "delete":
        manager.delete_snapshot(args.skill_name, args.version)
    elif args.command == "backup-all":
        manager.backup_all(args.message)
    elif args.command == "diff":
        manager.diff(args.skill_name, args.version)
    elif args.command == "rebuild-cache":
        manager.rebuild_cache(args.skill_name)
    elif args.command == "clear-cache":
        manager.clear_cache(args.skill_name)
    elif args.command == "status":
        manager.status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
