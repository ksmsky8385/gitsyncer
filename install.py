"""Install gitsyncer under the current user's home, without pip or sudo."""
import argparse
from datetime import datetime
from pathlib import Path
import shlex
import shutil
import sys

START = '# >>> gitsyncer >>>'
END = '# <<< gitsyncer <<<'


def update_rc(path, snippet):
    original = path.read_text() if path.exists() else ''
    if START in original or END in original:
        if original.count(START) != 1 or original.count(END) != 1:
            raise ValueError(f'Invalid gitsyncer markers in {path}; inspect manually.')
        start, end = original.index(START), original.index(END) + len(END)
        if start > end:
            raise ValueError(f'Invalid gitsyncer marker order: {path}')
        updated = original[:start] + snippet + original[end:]
    else:
        updated = original.rstrip('\n') + '\n\n' + snippet + '\n'
    if updated != original:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            stamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
            shutil.copy2(path, path.with_name(path.name + '.gitsyncer-backup-' + stamp))
        path.write_text(updated)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-shell-setup', action='store_true', help='Install without editing Bash/Zsh startup files')
    args = parser.parse_args()
    if sys.version_info < (3, 9):
        parser.error('Python 3.9 or later is required')
    source = Path(__file__).resolve().parent
    home = Path.home()
    destination = home / '.local/share/gitsyncer'
    bin_dir = home / '.local/bin'
    destination.mkdir(parents=True, exist_ok=True)
    bin_dir.mkdir(parents=True, exist_ok=True)
    for directory in ('gitsyncer', 'completions'):
        shutil.copytree(source / directory, destination / directory, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    (destination / 'README.md').write_text((source / 'README.md').read_text())
    # A concrete interpreter path also works on Termux, where /usr/bin/env may not exist.
    launcher = '#!' + sys.executable + '\nimport sys\nsys.path.insert(0, ' + repr(str(destination)) + ')\nfrom gitsyncer.cli import main\nraise SystemExit(main())\n'
    for name in ('gitsyncer', '깃싱커'):
        file = bin_dir / name
        if file.is_symlink():
            raise ValueError(f'Refusing to overwrite an existing symlink: {file}')
        if file.exists() and 'from gitsyncer.cli import main' not in file.read_text():
            raise ValueError(f'Existing unrelated executable: {file}')
        file.write_text(launcher)
        file.chmod(0o755)
    if not args.no_shell_setup:
        import os
        bash_source = shlex.quote(str(destination / 'completions/gitsyncer.bash'))
        zsh_source = shlex.quote(str(destination / 'completions/gitsyncer.zsh'))
        path_setup = 'case ":$PATH:" in\n  *":$HOME/.local/bin:"*) ;;\n  *) export PATH="$HOME/.local/bin:$PATH" ;;\nesac'
        update_rc(home / '.bashrc', START + '\n' + path_setup + '\nsource ' + bash_source + '\n' + END)
        zshrc = Path(os.environ.get('ZDOTDIR') or home).expanduser() / '.zshrc'
        update_rc(zshrc, START + '\n' + path_setup + '\nif ! (( $+functions[compdef] )); then\n  autoload -Uz compinit\n  compinit\nfi\nsource ' + zsh_source + '\n' + END)
    print(f'Installed: {bin_dir / "gitsyncer"} (alias: 깃싱커)')
    print('Open a new terminal, or reload ~/.bashrc / ${ZDOTDIR:-$HOME}/.zshrc.')
    print('Repository registrations are preserved. Run: gitsyncer status')


if __name__ == '__main__':
    main()
