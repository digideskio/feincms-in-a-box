from __future__ import print_function

import os
import platform
import random

from fabric.api import cd, env, local, run, task
from fabric.colors import green, red


CONFIG = {
    'host': 'deploy@',
    'project': 'box',
    'branch': 'master',
}


CONFIG.update({
    'sass': '{project}/static/{project}'.format(**CONFIG),
    'service': 'www-{project}'.format(**CONFIG),
    'folder': 'www/{project}/'.format(**CONFIG),
})


env.forward_agent = True
env.hosts = [CONFIG['host']]


def _configure(fn):
    def _dec(string, *args, **kwargs):
        return fn(string.format(**CONFIG), *args, **kwargs)
    return _dec


local = _configure(local)
cd = _configure(cd)
run = _configure(run)


@task
def dev():
    import socket
    from threading import Thread
    jobs = [
        Thread(target=watch_styles),
        Thread(target=runserver),
    ]
    try:
        socket.create_connection(('localhost', 6379), timeout=0.1).close()
    except socket.error:
        jobs.append(Thread(target=lambda: local('redis-server')))
    [j.start() for j in jobs]
    [j.join() for j in jobs]


@task(alias='ws')
def watch_styles():
    local('bundle exec compass watch {sass}')


@task(alias='rs')
def runserver(port=8000):
    local('venv/bin/python -Wall manage.py runserver 0.0.0.0:{}'.format(port))


@task
def deploy_styles():
    local('bundle exec compass clean {sass}')
    local('bundle exec compass compile -s compressed {sass}')
    local('scp -r {sass}/stylesheets {host}:{folder}static/{project}/')


@task
def deploy_code():
    local('flake8 .')
    local('git push origin {branch}')
    with cd('{folder}'):
        run('git fetch')
        run('git reset --hard origin/{branch}')
        run('find . -name "*.pyc" -delete')
        run('venv/bin/pip install -r requirements/live.txt')
        run('venv/bin/python manage.py syncdb')
        run('venv/bin/python manage.py migrate')
        run('venv/bin/python manage.py collectstatic --noinput')
        run('sudo service {service} restart')


@task
def deploy():
    deploy_styles()
    deploy_code()


@task
def setup():
    if os.path.exists('venv'):
        print(red('It seems that this project is already set up, aborting.'))
        return 1

    local('virtualenv venv')
    if platform.system() == 'Darwin' and platform.mac_ver()[0] >= '10.9':
        local(
            'export CFLAGS=-Qunused-arguments'
            '&& export CPPFLAGS=-Qunused-arguments'
            '&& venv/bin/pip install -r requirements/dev.txt')
    else:
        local('venv/bin/pip install -r requirements/dev.txt')

    with open('box/local_settings.py', 'w') as f:
        rand = random.SystemRandom()
        chars = 'abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)'
        secret_key = ''.join(rand.choice(chars) for i in range(50))
        f.write(
            'SECRET_KEY = \'%s\'\n'
            'ALLOWED_HOSTS = [\'*\']\n'
            'RAVEN_CONFIG = {}\n' % secret_key)

    local('venv/bin/python manage.py syncdb --all --noinput')
    local('venv/bin/python manage.py migrate --all --fake')
    local('bundle install --path .bundle/gems')

    print(green('Initial setup has completed successfully!', bold=True))
    print(green('Next steps:'))
    print(green(
        '- Create a superuser: venv/bin/python manage.py createsuperuser'))
    print(green('- Run the development server: fab dev'))
