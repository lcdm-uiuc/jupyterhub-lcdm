from tornado import gen
from dockerspawner import DockerSpawner
import os
import shutil
from traitlets import Unicode

# urllib3 complains that we're making unverified HTTPS connections to swarm,
# but this is ok because we're connecting to swarm via 127.0.0.1. I don't
# actually want swarm listening on a public port, so I don't want to connect
# to swarm via the host's FQDN, which means we can't do fully verified HTTPS
# connections. To prevent the warning from appearing over and over and over
# again, I'm just disabling it for now.
import requests
requests.packages.urllib3.disable_warnings()


class SwarmSpawner(DockerSpawner):

    container_ip = '0.0.0.0'

    singleuser = Unicode('jovyan', config=True)

    root_dir = Unicode('/export/home', config=True)

    @gen.coroutine
    def lookup_node_name(self):
        """Find the name of the swarm node that the container is running on."""
        containers = yield self.docker('containers', all=True)
        for container in containers:
            if container['Id'] == self.container_id:
                name, = container['Names']
                node, container_name = name.lstrip("/").split("/")
                raise gen.Return(node)

    @gen.coroutine
    def start(self, image=None, extra_create_kwargs=None, extra_host_config=None):
        # look up mapping of node names to ip addresses
        info = yield self.docker('info')
        num_nodes = int(info['SystemStatus'][3][1])
        node_info = info['SystemStatus'][4::9]
        self.node_info = {}
        for i in range(num_nodes):
            node, ip_port = node_info[i]
            self.node_info[node.strip()] = ip_port.strip().split(":")[0]
        self.log.debug("Swarm nodes are: {}".format(self.node_info))

        # specify extra host configuration
        if extra_host_config is None:
            extra_host_config = {}
#        if 'mem_limit' not in extra_host_config:
#            extra_host_config['mem_limit'] = '8g'

        # specify extra creation options
        if extra_create_kwargs is None:
            extra_create_kwargs = {}
        if 'working_dir' not in extra_create_kwargs:
            extra_create_kwargs['working_dir'] = "/home/{}".format(self.singleuser)

        # create and set permissions of home dir if it doesn't exist
        user_dir = os.path.join(self.root_dir, self.user.name)
        if not os.path.exists(user_dir):
            os.makedirs(user_dir)
        os.chown(user_dir, 1000, 100)
        
        # start the container
        yield DockerSpawner.start(
            self, image=image,
            extra_create_kwargs=extra_create_kwargs,
            extra_host_config=extra_host_config)

        # figure out what the node is and then get its ip
        name = yield self.lookup_node_name()
        self.user.server.ip = self.node_info[name]
        self.log.info("{} was started on {} ({}:{})".format(
            self.container_name, name, self.user.server.ip, self.user.server.port))

        self.log.info(self.env)
