from vcd.client.vcd_client import VcdClient, BasicLoginCredentials
import yaml


class OpsBase:
    _config_file = 'samples/config.yaml'
    _config_yaml = None

    def __init__(self):
        with open(self._config_file, 'r') as f:
            self._config_yaml = yaml.safe_load(f)

        self.host = self._config_yaml['vcd']['host']
        self.org = self._config_yaml['vcd']['org']
        self.user = self._config_yaml['vcd']['user']
        self.password = self._config_yaml['vcd']['password']

        self.client = VcdClient(host=self.host,
                                verify_ssl=False,
                                log_bodies=True,
                                log_headers=True)

    def login(self):
        creds = BasicLoginCredentials(user=self.user,
                                      org=self.org,
                                      password=self.password)
        self.client.set_credentials(creds)

    def logout(self):
        self.client.logout()

    def create(self):
        pass

    def read(self, href):
        pass

    def update(self, resource):
        pass

    def delete(self, href):
        pass

    def query(self, href=None):
        pass
