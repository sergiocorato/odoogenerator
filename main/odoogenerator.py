import odoorpc
import json
import subprocess
import time
import os
import signal


class Connection:

    def load_config(self, version, file_path=False):
        if not file_path:
            local_path = os.path.join(
                os.path.expanduser('~'),
                'Sviluppo',
                'srvmngt',
                'odoogenerator_config',
                'odoo_{}.json'.format(version)
            )
            if not os.path.exists(local_path):
                raise Exception('Unable to find configuration file for version: %s' % version)
            file_path = local_path
        f = open(file_path)
        data = json.load(f)
        f.close()
        return data

    def __init__(self, version):
        self.data = self.load_config(version)
        self.repository = self.data["repository"][0]
        self.options = self.data["options"][0]
        self.queue_job = self.data["queue_job"][0]
        self.python = self.data["python"][0]
        self.requirements = self.data["requirements"][0]
        self.path = os.path.expanduser('~')
        self.version = version
        self.venv_path = os.path.join(self.path, 'Sviluppo', 'Odoo')
        self.pg_bin_path = '/usr/lib/postgresql/15/bin/'
        # todo get from system function
        # if self.db_port in [
        # '5439', '5440', '5441'] else ''

    def odoo_connect(self):
        self.client = odoorpc.ODOO(
            host="localhost",
            protocol="jsonrpc+ssl", port=self.options["http_port"]
        )
        self.client.login(
            db=self.options["database"],
            login=self.options["db_user"],
            password=self.options["admin_passwd"],
        )

    def _create_venv(self, branch=False):
        venv_path = '%s/%s%s' % (
            self.venv_path, 'odoo',
            self.version)
        py_version = self.data.get('python')[0].get('version')
        odoo_repo = 'https://github.com/OCA/OCB.git'
        if not os.path.isdir(venv_path):
            subprocess.Popen(['mkdir -p %s' % venv_path], shell=True).wait()
            subprocess.Popen([
                'python -m venv %s' % venv_path],
                cwd=venv_path, shell=True).wait()
        if not os.path.isdir(os.path.join(venv_path, 'odoo')):
            subprocess.Popen([
                'cd %s && git clone --single-branch %s -b %s --depth 1 odoo' % (
                    venv_path, odoo_repo, branch or self.version)],
                cwd=venv_path, shell=True).wait()
        elif branch:
            subprocess.Popen(['cd %s/odoo && git reset --hard origin/%s && git pull '
                              'origin %s' % (
                                  venv_path, self.version, branch)],
                             cwd=venv_path, shell=True).wait()
        else:
            subprocess.Popen(['cd %s/odoo && git reset --hard origin/%s && git pull '
                              '&& git reset --hard origin/%s' % (
                              venv_path, self.version, self.version)],
                             cwd=venv_path, shell=True).wait()
        commands = [
            'bin/pip install -r odoo/requirements.txt',
            'cd odoo && ../bin/pip install -e . ',
        ]
        for command in commands:
            subprocess.Popen(command, cwd=venv_path, shell=True).wait()
        extra_paths = ['%s/addons-extra' % venv_path,
                       '%s/repos' % venv_path]
        for path in extra_paths:
            if not os.path.isdir(path):
                process = subprocess.Popen(
                    'mkdir %s' % path, cwd=venv_path, shell=True)
                process.wait()
        if os.path.isfile(os.path.join(venv_path, 'migration.log')):
            process = subprocess.Popen(
                'rm %s' % 'migration.log', cwd=venv_path, shell=True)
            process.wait()
        repos = config.load_config('openupgrade_repos.yml', self.version)
        for repo_name in repos:
            repo_text = repos.get(repo_name)
            repo = repo_text.split(' ')[0]
            repo_version = repo_text.split(' ')[1]
            if not os.path.isdir('%s/repos/%s' % (venv_path, repo_name)):
                process = subprocess.Popen([
                    'git clone %s --single-branch -b %s --depth 1 '
                    '%s/repos/%s'
                    % (repo, repo_version, venv_path, repo_name)
                ], cwd=venv_path, shell=True)
                process.wait()
            process = subprocess.Popen([
                'cd %s/repos/%s '
                '&& git remote set-branches --add origin %s '
                '&& git fetch '
                '&& git checkout origin/%s' % (
                    venv_path, repo_name,
                    repo_version,
                    repo_version)
            ], cwd=venv_path, shell=True)
            process.wait()
            # copy modules to create an unique addons path
            for root, dirs, files in os.walk(
                    '%s/repos/%s/' % (venv_path, repo_name)):
                for d in dirs:
                    if d not in ['.git', 'setup']:
                        process = subprocess.Popen([
                            "cp -rf %s/repos/%s/%s %s/addons-extra/" %(
                                venv_path, repo_name, d,
                                venv_path)
                        ], cwd=venv_path, shell=True)
                        process.wait()
                break

    #### TODO ####

    def start_odoo(self, version, update=False):
        """
        :param version: odoo version to start (8.0, 9.0, 10.0, ...)
        :param update: if True odoo will be updated with -u all and stopped
        :param migrate: if True start odoo with openupgrade repo
        :return: odoo instance in self.client if not updated, else nothing
        """
        venv_path = '%s/%s%s' % (
            self.venv_path, 'standard',
            version)
        load = 'web'
        if version == '10.0':
            load = 'web,web_kanban'
        if version == '12.0':
            load = 'base,web'
        executable = 'openerp-server' if version in ['7.0', '8.0', '9.0'] else 'odoo'
        bash_command = "bin/%s " \
                       "--db_port=%s --xmlrpc-port=%s " \
                       "--logfile=%s/migration.log " \
                       "--limit-time-cpu=600 --limit-time-real=1200 "\
                       "--addons-path=" \
                       "%s/odoo/addons,%s/addons-extra%s " \
                       "--load=%s " % (
                        executable, self.db_port, self.xmlrpc_port, venv_path,
                        venv_path, venv_path,
                        (',%s/odoo/odoo/addons' % venv_path if version not in [
                            '7.0', '8.0', '9.0'] else ''),
                        load)
        cwd_path = '%s/' % venv_path
        if version != '7.0':
            bash_command += "--data-dir=%s/data_dir " % venv_path
        if update:
            bash_command += " -u all -d %s --stop-after-init" % self.db
        process = subprocess.Popen(
            bash_command.split(), stdout=subprocess.PIPE, cwd=cwd_path)
        self.pid = process.pid
        if update:
            process.wait()
        else:
            time.sleep(15)
            self.odoo_connect()
        time.sleep(5)

    def stop_odoo(self):
        if self.pid:
            os.kill(self.pid, signal.SIGTERM)
            time.sleep(5)

    def dump_database(self, version):
        pg_bin_path = self.pg_bin_path
        process = subprocess.Popen(
            ['%spg_dump -O -p %s -d %s | gzip > %s/database.%s.gz' % (
                 pg_bin_path, self.db_port, self.db, self.venv_path, version
             )], shell=True)
        process.wait()

    def restore_filestore(self, from_version, to_version):
        dump_file = os.path.join(self.path, 'filestore.tar')
        if os.path.isfile(dump_file):
            process = subprocess.Popen(
                ['mv %s %s/filestore.%s.tar' % (
                    dump_file, self.venv_path, from_version)], shell=True)
            process.wait()
        dump_file = os.path.join(
            self.venv_path, 'filestore.%s.tar' % from_version)
        filestore_path = '%s/openupgrade%s/data_dir/filestore' % (
            self.venv_path, to_version)
        if not os.path.isdir(filestore_path):
            process = subprocess.Popen([
                'mkdir -p %s' % filestore_path], shell=True)
            process.wait()
        process = subprocess.Popen([
            'tar -zxvf %s -C %s/openupgrade%s/data_dir/filestore/' % (
                dump_file, self.venv_path, to_version)], shell=True)
        process.wait()

    def dump_filestore(self, version):
        process = subprocess.Popen([
            'cd %s/openupgrade%s/data_dir/filestore && '
            'tar -zcvf %s/filestore.%s.tar %s' % (
                self.venv_path, version, self.venv_path, version, self.db)
        ], shell=True)
        process.wait()

    def restore_db(self, from_version):
        pg_bin_path = self.pg_bin_path
        process = subprocess.Popen(
            ['%sdropdb -p %s %s' % (pg_bin_path, self.db_port, self.db)],
            shell=True)
        process.wait()
        process = subprocess.Popen(
            ['%screatedb -p %s %s' % (
                pg_bin_path, self.db_port, self.db)], shell=True)
        process.wait()
        dump_file = os.path.join(self.path, 'database.gz')
        if os.path.isfile(dump_file):
            process = subprocess.Popen(
                ['mv %s %s/database.%s.gz' % (
                    dump_file, self.venv_path, from_version)], shell=True)
            process.wait()
        dump_file = os.path.join(
            self.venv_path, 'database.%s.gz' % from_version)

        process = subprocess.Popen(
            ['cat %s | gunzip | %spsql -U $USER -p %s -d %s ' % (
                dump_file, pg_bin_path, self.db_port, self.db)], shell=True)
        process.wait()

    def auto_install_modules(self, version):
        self.start_odoo(version)
        module_obj = self.client.env['ir.module.module']
        if version == '12.0':
            self.remove_modules('upgrade')
        receipt = self.receipts[version]
        for modules in receipt:
            module_list = modules.get('auto_install', False)
            if module_list:
                for module_pair in module_list:
                    module_to_check = module_pair.split(' ')[0]
                    module_to_install = module_pair.split(' ')[1]
                    if module_obj.search([
                            ('name', '=', module_to_check),
                            ('state', '=', 'installed')]):
                        self.client.env.install(module_to_install)
        self.stop_odoo()

    def uninstall_modules(self, version, before_migration=False, after_migration=False):
        self.start_odoo(version)
        if version == '12.0':
            self.remove_modules('upgrade')
        receipt = self.receipts[version]
        for modules in receipt:
            if after_migration:
                modules_to_uninstall = modules.get('uninstall_after_migration', False)
                if modules_to_uninstall:
                    for module in modules_to_uninstall:
                        self.install_uninstall_module(module, install=False)
            if before_migration:
                modules_to_uninstall = modules.get('uninstall_before_migration', False)
                if modules_to_uninstall:
                    for module in modules_to_uninstall:
                        self.install_uninstall_module(module, install=False)
        self.stop_odoo()

    def delete_old_modules(self, version):
        receipt = self.receipts[version]
        if [modules.get('delete', False) for modules in receipt]:
            self.start_odoo(version)
            module_obj = self.client.env['ir.module.module']
            for modules in receipt:
                module_list = modules.get('delete', False)
                if module_list:
                    for module in module_list:
                        module = module_obj.search([
                            ('name', '=', module)])
                        if module:
                            module_obj.unlink(module.id)
            self.stop_odoo()

    def remove_modules(self, module_state=''):
        if module_state == 'upgrade':
            state = ['to upgrade', ]
        else:
            state = ['to remove', 'to install']
        module_obj = self.client.env['ir.module.module']
        modules = module_obj.search([('state', 'in', state)])
        msg_modules = ''
        msg_modules_after = ''
        if modules:
            msg_modules = str([x.name for x in modules])
        for module in modules:
            module.button_uninstall_cancel()
        modules_after = module_obj.search(
            [('state', '=', 'to upgrade')])
        if modules_after:
            msg_modules_after = str([x.name for x in modules_after])
        print('Modules: %s' % msg_modules)
        print('Modules after: %s' % msg_modules_after)

    def install_uninstall_module(self, module, install=True):
        module_obj = self.client.env['ir.module.module']
        to_remove_modules = module_obj.search(
            [('state', '=', 'to remove')])
        for module_to_remove in to_remove_modules:
            module_to_remove.button_uninstall_cancel()
        state = self.client.env.modules(module)
        if state:
            if install:
                self.client.env.install(module)
            elif state.get('installed', False) or state.get('to upgrade', False)\
                    or state.get('uninstallable'):
                module_id = module_obj.search([('name', '=', module)])
                if module_id:
                    try:
                        module_id.button_immediate_uninstall()
                        print('Module %s uninstalled' % module)
                        module_id.unlink()
                    except Exception as e:
                        print('Module %s not uninstalled for %s' % (module, e))
                        pass
                else:
                    print('Module %s not found' % module)