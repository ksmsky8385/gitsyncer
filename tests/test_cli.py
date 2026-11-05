import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from gitsyncer import cli

SOURCE = Path(__file__).resolve().parents[1]


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.home = self.base/'home'; self.home.mkdir()
        environment = {'HOME':str(self.home),'GITSYNCER_CONFIG':str(self.base/'config/repos.json'),
                       'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':os.devnull,
                       'GIT_AUTHOR_NAME':'Tester','GIT_AUTHOR_EMAIL':'test@example.invalid',
                       'GIT_COMMITTER_NAME':'Tester','GIT_COMMITTER_EMAIL':'test@example.invalid'}
        self.env=patch.dict(os.environ,environment);self.env.start();self.addCleanup(self.env.stop)

    def git(self,path,*args):
        return subprocess.check_output(['git','-C',str(path),*args],stderr=subprocess.PIPE,text=True).strip()

    def make_repo(self,name,folder=None):
        path=(folder or self.base)/name; path.mkdir(parents=True)
        self.git(path,'init','-b','main')
        (path/'tracked.txt').write_text('initial\n')
        self.git(path,'add','.'); self.git(path,'commit','-m','initial')
        return path

    def remote(self,path):
        remote=self.base/(path.name+'.git')
        subprocess.run(['git','init','--bare','-b','main',str(remote)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        self.git(path,'remote','add','origin',str(remote))
        self.git(path,'push','-u','origin','main')
        return remote

    def capture(self,func,*args,**kwargs):
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):
            result=func(*args,**kwargs)
        return result,stream.getvalue()

    def test_register_subdirectory_spaces_duplicate_and_remove(self):
        repo=self.make_repo('my repo');(repo/'src').mkdir()
        self.capture(cli.add,str(repo/'src'))
        self.assertEqual(cli.load(),{'my repo':str(repo)})
        other=self.make_repo('my repo',self.base/'other')
        with self.assertRaises(cli.Error): self.capture(cli.add,str(other))
        self.capture(cli.remove,'my repo')
        self.assertTrue(repo.exists());self.assertEqual(cli.load(),{})

    def test_reject_nonrepo_reserved_name_and_corrupt_registry(self):
        with self.assertRaises(cli.Error): cli.add(str(self.home))
        with self.assertRaises(cli.Error): cli.add(str(self.make_repo('all')))
        path=cli.config_path();path.parent.mkdir();path.write_text('broken')
        with self.assertRaises(cli.Error): cli.load()

    def test_push_add_modify_delete_and_message(self):
        repo=self.make_repo('project');remote=self.remote(repo)
        (repo/'tracked.txt').unlink();(repo/'new file.txt').write_text('new')
        with patch('builtins.input',return_value='Add new file and delete old'):
            cli.push_one(repo,'project')
        self.assertEqual(self.git(remote,'log','-1','--format=%s'),'Add new file and delete old')
        self.assertEqual(self.git(remote,'ls-tree','--name-only','HEAD'),'new file.txt')
        self.assertFalse(cli.info(repo)['dirty'])

    def test_blank_message_preserves_index(self):
        repo=self.make_repo('project');self.remote(repo)
        (repo/'tracked.txt').write_text('changed')
        before=self.git(repo,'diff','--cached')
        with patch('builtins.input',return_value=''):
            cli.push_one(repo,'project')
        self.assertEqual(self.git(repo,'diff','--cached'),before)
        self.assertTrue(cli.info(repo)['dirty'])

    def test_push_existing_commit_no_prompt(self):
        repo=self.make_repo('project');remote=self.remote(repo)
        (repo/'tracked.txt').write_text('committed')
        self.git(repo,'commit','-am','already committed')
        with patch('builtins.input',side_effect=AssertionError('unexpected prompt')):
            cli.push_one(repo,'project',batch=True)
        self.assertEqual(self.git(repo,'rev-parse','HEAD'),self.git(remote,'rev-parse','HEAD'))

    def test_sorted_batch_skips_clean_and_continues_failure(self):
        repos=[self.make_repo(n) for n in ['zeta','alpha','clean','broken']]
        for repo in repos:
            self.remote(repo);self.capture(cli.add,str(repo))
            if repo.name not in ['clean','broken']: (repo/'tracked.txt').write_text('changed')
        self.git(repos[-1],'checkout','--detach')
        prompts=[]
        def message(prompt): prompts.append(prompt);return 'update'
        with patch('builtins.input',side_effect=message):
            result,out=self.capture(cli.synchronize,'push','all')
        self.assertEqual(result,1)
        self.assertEqual(len(prompts),2)
        self.assertIn('[alpha]',prompts[0]);self.assertIn('[zeta]',prompts[1])
        self.assertIn('clean',out);self.assertIn('broken',out)

    def test_fetch_and_pull(self):
        repo=self.make_repo('project');remote=self.remote(repo)
        peer=self.base/'peer';self.git(self.base,'clone',str(remote),str(peer))
        (peer/'new').write_text('remote');self.git(peer,'add','.');self.git(peer,'commit','-m','peer');self.git(peer,'push')
        cli.pull_one(repo)
        self.assertEqual((repo/'new').read_text(),'remote')

    def test_dirty_and_divergent_pull_preserves_work(self):
        repo=self.make_repo('project');remote=self.remote(repo)
        (repo/'tracked.txt').write_text('local')
        with self.assertRaises(cli.Error):cli.pull_one(repo)
        self.assertEqual((repo/'tracked.txt').read_text(),'local')
        self.git(repo,'commit','-am','local')
        local=self.git(repo,'rev-parse','HEAD')
        peer=self.base/'peer';self.git(self.base,'clone',str(remote),str(peer))
        (peer/'tracked.txt').write_text('remote');self.git(peer,'commit','-am','remote');self.git(peer,'push')
        with self.assertRaises(cli.Error):cli.pull_one(repo)
        self.assertEqual(self.git(repo,'rev-parse','HEAD'),local)
        self.assertEqual((repo/'tracked.txt').read_text(),'local')

    def test_failed_push_keeps_commit(self):
        repo=self.make_repo('project');remote=self.remote(repo)
        peer=self.base/'peer';self.git(self.base,'clone',str(remote),str(peer))
        (peer/'tracked.txt').write_text('remote');self.git(peer,'commit','-am','remote');self.git(peer,'push')
        (repo/'tracked.txt').write_text('local')
        with patch('builtins.input',return_value='local work'):
            with self.assertRaises(cli.Error):cli.push_one(repo,'project')
        self.assertEqual(self.git(repo,'log','-1','--format=%s'),'local work')
        self.assertEqual((repo/'tracked.txt').read_text(),'local')

    def test_first_commit_push_and_ambiguous_remote(self):
        repo=self.base/'empty';repo.mkdir();self.git(repo,'init','-b','main')
        remote=self.base/'empty.git';self.git(self.base,'init','--bare','-b','main',str(remote))
        self.git(repo,'remote','add','origin',str(remote));(repo/'new').write_text('hello')
        with patch('builtins.input',return_value='first'):cli.push_one(repo,'empty')
        self.assertEqual(self.git(remote,'log','-1','--format=%s'),'first')
        self.git(repo,'branch','--unset-upstream');self.git(repo,'remote','add','other',str(remote))
        with self.assertRaises(cli.Error):cli.destination(repo,'main')

    def test_path_completion_with_spaces(self):
        (self.home/'my folder').mkdir()
        self.assertEqual(cli.path_matches('~'),['~/'])
        self.assertEqual(cli.path_matches('~/my'),['~/my folder/'])
        self.assertEqual(cli.path_matches(str(self.home)+'/my'),[str(self.home)+'/my folder/'])

    def test_status_no_network_and_noninteractive_cli(self):
        repo=self.make_repo('project');self.capture(cli.add,str(repo))
        result=subprocess.run([sys.executable,'-m','gitsyncer','status'],cwd=SOURCE,capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0)
        self.assertIn('project',result.stdout)
        self.assertNotIn('[a]',result.stdout)

    def test_installer_idempotent_and_completion_syntax(self):
        env=dict(os.environ);env['ZDOTDIR']=str(self.home)
        (self.home/'.bashrc').write_text('# existing\n')
        for _ in range(2):
            subprocess.run(['sh',str(SOURCE/'install.sh')],env=env,check=True,stdout=subprocess.DEVNULL)
        for rc in ['.bashrc','.zshrc']:
            self.assertEqual((self.home/rc).read_text().count('# >>> gitsyncer >>>'),1)
        self.assertIn('# existing',(self.home/'.bashrc').read_text())
        for name in ['gitsyncer','깃싱커']:
            out=subprocess.check_output([str(self.home/'.local/bin'/name),'--version'],text=True)
            self.assertIn('0.1.0',out)
        subprocess.run(['bash','-n',str(SOURCE/'completions/gitsyncer.bash')],check=True)
        subprocess.run(['zsh','-n',str(SOURCE/'completions/gitsyncer.zsh')],check=True)

    def test_bash_and_zsh_registration(self):
        bash=f'source "{SOURCE}/completions/gitsyncer.bash"; COMP_WORDS=(gitsyncer ""); COMP_CWORD=1; _gitsyncer_complete; printf "%s\\n" "${{COMPREPLY[@]}}"'
        out=subprocess.check_output(['bash','--noprofile','--norc','-c',bash],text=True)
        self.assertIn('status',out);self.assertIn('push',out)
        zsh=f'autoload -Uz compinit; compinit -d "{self.home}/.zcompdump"; source "{SOURCE}/completions/gitsyncer.zsh"; print $_comps[gitsyncer]'
        out=subprocess.check_output(['zsh','-f','-c',zsh],text=True)
        self.assertIn('_gitsyncer',out)


if __name__=='__main__':unittest.main()
