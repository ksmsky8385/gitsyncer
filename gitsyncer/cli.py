"""Interactive multi-repository Git synchronization."""
import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unicodedata


class Error(Exception):
    pass


def config_path():
    base = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))
    return Path(os.environ.get('GITSYNCER_CONFIG', str(base / 'gitsyncer/repos.json'))).expanduser()


def load():
    path = config_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in data.items()):
            raise ValueError('expected name/path mapping')
        return data
    except (ValueError, OSError) as exc:
        raise Error(f'Cannot read repository registry: {path}: {exc}') from exc


@contextmanager
def registry_lock():
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix('.lock').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def save(data):
    path = config_path()
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.repos-')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def git(path, *args, check=True, live=False):
    environment = dict(os.environ, LC_ALL='C', LANG='C', LANGUAGE='C')
    result = subprocess.run(['git', '-C', str(path), *args], text=True, env=environment,
                            stdout=None if live else subprocess.PIPE,
                            stderr=None if live else subprocess.PIPE)
    if check and result.returncode:
        detail = (result.stderr or '').strip() if not live else 'See the Git output above.'
        raise Error(f'git {args[0]} failed ({result.returncode}): {detail}')
    return result


def root_path(value):
    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        raise Error(f'Directory not found: {path}')
    result = git(path, 'rev-parse', '--show-toplevel', check=False)
    if result.returncode:
        raise Error(f'Not a Git working repository: {path}')
    return Path(result.stdout.strip()).resolve()


def registered_path(value):
    path = Path(value)
    root = root_path(path)
    if root != path.resolve():
        raise Error(f'Registered path is no longer a repository root: {path}')
    return root


def path_matches(text):
    if text == "~":
        return ["~/"]
    expanded = os.path.expanduser(text)
    base, prefix = os.path.split(expanded)
    directory = Path(base or '.')
    original_base = text[:-len(prefix)] if prefix else text
    try:
        return sorted(original_base + p.name + '/' for p in directory.iterdir()
                      if p.is_dir() and p.name.startswith(prefix)
                      and (prefix.startswith('.') or not p.name.startswith('.')))
    except OSError:
        return []


def ask_path():
    prompt = 'Repository path (Tab to complete; Enter to cancel): '
    try:
        import readline
    except ImportError:
        if sys.stdin.isatty() and shutil.which('bash'):
            result = subprocess.run(['bash', '-c', 'IFS= read -e -r -p "$1" value && printf "%s" "$value"',
                                     'gitsyncer', prompt], stdout=subprocess.PIPE, text=True)
            return result.stdout if result.returncode == 0 else ''
        print('Readline is unavailable. You can use shell completion with add <path><Tab>.')
        return input(prompt)
    previous, delimiters = readline.get_completer(), readline.get_completer_delims()
    def complete(text, state):
        matches = path_matches(text)
        return matches[state] if state < len(matches) else None
    readline.set_completer_delims('\n')
    readline.set_completer(complete)
    readline.parse_and_bind('bind ^I rl_complete' if 'libedit' in (readline.__doc__ or '') else 'tab: complete')
    try:
        return input(prompt)
    finally:
        readline.set_completer(previous)
        readline.set_completer_delims(delimiters)


def add(value=None):
    value = value if value is not None else ask_path()
    if not value:
        print('Registration cancelled'); return
    path = root_path(value)
    name = path.name
    if name == 'all' or name.startswith('-') or any(ord(c) < 32 for c in name):
        raise Error('Repository names cannot be all, start with a hyphen, or contain control characters.')
    with registry_lock():
        data = load()
        if name in data and data[name] != str(path):
            raise Error(f'A different repository is already registered with this name: {name} → {data[name]}')
        data[name] = str(path)
        save(data)
    print(f'Registered: {name} → {path}')


def remove(name=None):
    name = name if name is not None else input('Repository name to remove (Enter to cancel): ')
    if not name:
        return
    with registry_lock():
        data = load()
        if name not in data:
            raise Error(f'Repository is not registered: {name}')
        del data[name]
        save(data)
    print(f'Removed registration: {name} (the directory is unchanged)')


def info(path):
    branch = git(path, 'symbolic-ref', '--quiet', '--short', 'HEAD', check=False).stdout.strip()
    dirty = bool(git(path, 'status', '--porcelain', '-z').stdout)
    upstream = git(path, 'rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}', check=False)
    ahead = behind = None
    if upstream.returncode == 0:
        counts = git(path, 'rev-list', '--left-right', '--count', 'HEAD...@{upstream}', check=False)
        if counts.returncode == 0:
            ahead, behind = map(int, counts.stdout.split())
    return {'branch': branch, 'dirty': dirty, 'upstream': upstream.stdout.strip() if upstream.returncode == 0 else '',
            'ahead': ahead, 'behind': behind}


def display_width(text):
    return sum(0 if unicodedata.combining(char) else
               2 if unicodedata.east_asian_width(char) in ('W', 'F') else 1
               for char in text)


def print_table(rows):
    rows = [[str(cell).replace('\t', ' ').replace('\n', ' ').replace('\r', ' ')
             for cell in row] for row in rows]
    widths = [max(display_width(row[column]) for row in rows)
              for column in range(len(rows[0]) - 1)]
    for row in rows:
        print('  '.join(cell + ' ' * (widths[column] - display_width(cell))
                        for column, cell in enumerate(row[:-1])) + '  ' + row[-1])


def status(interactive=True):
    while True:
        data = load()
        rows = [('NAME', 'BRANCH', 'STATE', 'AHEAD/BEHIND (local refs)', 'PATH')]
        for name in sorted(data):
            try:
                state = info(registered_path(data[name]))
                counts = f"{state['ahead']}/{state['behind']}" if state['ahead'] is not None else '-'
                rows.append((name, state['branch'] or '(detached)',
                             'modified' if state['dirty'] else 'clean', counts, data[name]))
            except Error as exc:
                rows.append((name, '-', 'error', '-', f'{data[name]} (Error: {exc})'))
        print_table(rows)
        if not data:
            print('No repositories registered. Use add <path> to register one.')
        if not interactive or not sys.stdin.isatty() or not sys.stdout.isatty():
            return
        action = input('\n[a] Add repository  [d] Remove registration  [r] Refresh  [Enter/q] Quit > ').strip().lower()
        if action in ('', 'q'):
            return
        try:
            if action == 'a': add()
            elif action == 'd': remove()
            elif action != 'r': print('Choose a, d, r, or q.')
        except Error as exc:
            print(f'Error: {exc}', file=sys.stderr)


def ensure_ready(path):
    state = info(path)
    if not state['branch']:
        raise Error('Cannot synchronize a detached HEAD. Check out a branch first.')
    if git(path, 'ls-files', '-u').stdout:
        raise Error('Unresolved conflicts must be resolved first.')
    for name in ['MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'rebase-merge', 'rebase-apply', 'sequencer']:
        marker = Path(git(path, 'rev-parse', '--git-path', name).stdout.strip())
        if not marker.is_absolute(): marker = path / marker
        if marker.exists(): raise Error('Finish the in-progress merge, rebase, or cherry-pick first.')
    return state


def destination(path, branch):
    remote = git(path, 'config', '--get', f'branch.{branch}.remote', check=False).stdout.strip()
    ref = git(path, 'config', '--get', f'branch.{branch}.merge', check=False).stdout.strip()
    remotes = git(path, 'remote').stdout.splitlines()
    if remote and ref:
        if remote not in remotes or not ref.startswith('refs/heads/'):
            raise Error('A valid remote branch upstream is required.')
        return remote, ref
    if len(remotes) != 1:
        raise Error('No remote or multiple remotes found. Configure a branch upstream in Git first.')
    return remotes[0], 'refs/heads/' + branch


def pull_one(path):
    state = ensure_ready(path)
    if state['dirty']:
        raise Error('Pull skipped: local changes exist. Commit or resolve them manually first.')
    remote, ref = destination(path, state['branch'])
    git(path, 'fetch', '--prune', remote, live=True)
    git(path, '-c', 'pull.rebase=false', '-c', 'rebase.autoStash=false',
        '-c', 'merge.autoStash=false', 'pull', '--ff-only', '--no-rebase',
        '--no-autostash', remote, ref, live=True)
    print('Pull complete')


def push_one(path, name, batch=False):
    state = ensure_ready(path)
    if batch and not state['dirty'] and state['ahead'] == 0:
        print('Skipped: no changes or outgoing commits'); return
    has_head = git(path, 'rev-parse', '--verify', 'HEAD', check=False).returncode == 0
    if not state['dirty'] and not has_head:
        print('Skipped: nothing to commit'); return
    remote, ref = destination(path, state['branch'])
    if state['dirty']:
        print(f'[{name}] Changes to be staged by git add .:')
        git(path, 'status', '--short', live=True)
        message = input(f'[{name}] Commit message (Enter to skip this repository): ').strip()
        if not message:
            print('Skipped (index unchanged)'); return
        # Prompt first so cancellation does not alter the index.
        git(path, 'add', '.', live=True)
        staged = git(path, 'diff', '--cached', '--quiet', check=False)
        if staged.returncode not in (0, 1):
            raise Error('Could not inspect staged changes')
        if staged.returncode == 1:
            git(path, 'commit', '-m', message, live=True)
        else:
            print('No changes can be committed here (for example, uncommitted submodule changes)')
    git(path, 'push', '--set-upstream', remote, f'HEAD:{ref}', live=True)
    print('Push complete')


def synchronize(command, target):
    data = load()
    if target != 'all' and target not in data:
        raise Error(f'Repository is not registered: {target}')
    names = sorted(data) if target == 'all' else [target]
    failures = []
    if not names: print('No repositories registered.')
    for name in names:
        print(f'\n=== {name} ===', flush=True)
        try:
            path = registered_path(data[name])
            if command == 'pull': pull_one(path)
            else: push_one(path, name, batch=target == 'all')
        except (Error, OSError) as exc:
            failures.append(name)
            print(f'Failed [{name}]: {exc}', file=sys.stderr)
    if failures:
        print('Failed repositories: ' + ', '.join(failures), file=sys.stderr)
    return 1 if failures else 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog='gitsyncer', description='Manage and synchronize multiple Git repositories from your terminal.')
    parser.add_argument('--version', action='version', version='gitsyncer 0.1.0')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('status', help='List repositories and open the registration menu')
    p.add_argument('--no-interactive', action='store_true')
    p.add_argument('action', nargs='?', choices=['add', 'remove'])
    p.add_argument('value', nargs='?')
    p = sub.add_parser('add', help='Register a repository path'); p.add_argument('path', nargs='?')
    p = sub.add_parser('remove', help='Remove a repository registration'); p.add_argument('name', nargs='?')
    for name in ['pull', 'push']:
        p = sub.add_parser(name, help=f'{name} all or a repository name')
        p.add_argument('target')
    sub.add_parser('_names', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        if args.command == '_names':
            print('\n'.join(sorted(load()))); return 0
        if not shutil.which('git'): raise Error('Git is not installed.')
        if args.command == 'add': add(args.path)
        elif args.command == 'remove': remove(args.name)
        elif args.command == 'status':
            if args.action == 'add': add(args.value)
            elif args.action == 'remove': remove(args.value)
            else: status(not args.no_interactive)
        else: return synchronize(args.command, args.target)
        return 0
    except (Error, OSError) as exc:
        print(f'Error: {exc}', file=sys.stderr); return 1
    except (KeyboardInterrupt, EOFError):
        print('\nCancelled.', file=sys.stderr); return 130


if __name__ == '__main__':
    raise SystemExit(main())
