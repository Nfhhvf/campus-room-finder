"""Fast-forward an unmodified main checkout, then restart with the same arguments."""
import os
import subprocess
import sys
from pathlib import Path

RESTART_FLAG = 'CAMPUS_ROOMS_RESTARTED'


def update_checkout(root):
    """Return (updated, message). Never reset, stash or overwrite local changes."""
    root = Path(root).resolve()
    environment = {**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GCM_INTERACTIVE': 'Never'}

    def git(*args):
        return subprocess.run(['git', '-C', str(root), *args], env=environment,
                              capture_output=True, text=True, timeout=15, check=False)

    try:
        actual = git('rev-parse', '--show-toplevel')
        if actual.returncode or Path(actual.stdout.strip()).resolve() != root:
            return False, 'Program updates need a Git clone. Using this copy.'
        branch = git('symbolic-ref', '--quiet', '--short', 'HEAD')
        if branch.returncode or branch.stdout.strip() != 'main':
            return False, 'Automatic updates are paused outside the main branch.'
        status = git('status', '--porcelain', '--untracked-files=normal')
        if status.returncode or status.stdout.strip():
            return False, 'Local changes found. Program update skipped; your files are preserved.'
        fetched = git('fetch', '--no-tags', 'origin', 'main')
        if fetched.returncode:
            return False, 'Could not check GitHub. Using the installed version.'
        target = git('rev-parse', '--verify', 'FETCH_HEAD^{commit}')
        head = git('rev-parse', '--verify', 'HEAD^{commit}')
        if target.returncode or head.returncode:
            return False, 'Could not read the update. Using the installed version.'
        revision = target.stdout.strip()
        if revision == head.stdout.strip():
            return False, 'Program is up to date.'
        if git('merge-base', '--is-ancestor', 'HEAD', revision).returncode:
            return False, 'Local history differs from GitHub. Update skipped; no commits changed.'
        # Reject code requiring unsupported Python syntax before changing files.
        tree = git('ls-tree', '-r', '--name-only', revision)
        if tree.returncode:
            return False, 'Could not inspect the update. Using the installed version.'
        for name in tree.stdout.splitlines():
            if name.endswith('.py'):
                contents = git('show', revision + ':' + name)
                if contents.returncode:
                    return False, 'Could not inspect the update. Using the installed version.'
                compile(contents.stdout, name, 'exec')
        # Check again after the download, in case a file was edited meanwhile.
        status = git('status', '--porcelain', '--untracked-files=normal')
        current = git('rev-parse', '--verify', 'HEAD^{commit}')
        if status.returncode or status.stdout.strip() or current.stdout != head.stdout:
            return False, 'Local files changed during the check. Program update skipped.'
        merged = git('-c', 'merge.autostash=false', 'merge', '--ff-only', '--no-edit',
                     '--no-overwrite-ignore', revision)
        if merged.returncode:
            return False, 'Could not apply the program update. No reset or stash was attempted.'
        return True, 'Program updated. Restarting...'
    except FileNotFoundError:
        return False, 'Git is unavailable. Using the installed version.'
    except subprocess.TimeoutExpired:
        return False, 'Program update check timed out. Continuing with this copy.'
    except (OSError, SyntaxError, UnicodeError):
        return False, 'The update could not be verified. Continuing with this copy.'


def before_launch(script, argv):
    root = Path(script).resolve().parent
    if os.environ.pop(RESTART_FLAG, None) == str(root):
        return
    if any(option in argv[1:] for option in ('--offline', '--demo', '--no-update', '--help', '-h')):
        return
    print('Checking program updates...', flush=True)
    updated, message = update_checkout(root)
    print(message, flush=True)
    if updated:
        os.environ[RESTART_FLAG] = str(root)
        os.execv(sys.executable, [sys.executable, str(Path(script).resolve()), *argv[1:]])
