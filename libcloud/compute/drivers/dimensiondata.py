# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Dimension Data Driver
"""

try:
    from lxml import etree as ET
except ImportError:
    from xml.etree import ElementTree as ET

from libcloud.compute.base import NodeDriver, Node
from libcloud.compute.base import NodeSize, NodeImage, NodeLocation
from libcloud.common.dimensiondata import (DimensionDataConnection,
                                           DimensionDataStatus)
from libcloud.common.dimensiondata import DimensionDataNetwork
from libcloud.common.dimensiondata import DimensionDataNetworkDomain
from libcloud.common.dimensiondata import DimensionDataVlan
from libcloud.common.dimensiondata import API_ENDPOINTS
from libcloud.common.dimensiondata import DEFAULT_REGION
from libcloud.common.dimensiondata import TYPES_URN
from libcloud.common.dimensiondata import SERVER_NS
from libcloud.common.dimensiondata import NETWORK_NS
from libcloud.utils.xml import fixxpath, findtext, findall
from libcloud.compute.types import NodeState, Provider


class DimensionDataNodeDriver(NodeDriver):
    """
    DimensionData node driver.
    """

    selected_region = None
    connectionCls = DimensionDataConnection
    name = 'DimensionData'
    website = 'http://www.dimensiondata.com/'
    type = Provider.DIMENSIONDATA
    features = {'create_node': ['password']}
    api_version = 1.0

    def __init__(self, key, secret=None, secure=True, host=None, port=None,
                 api_version=None, region=DEFAULT_REGION, **kwargs):

        if region not in API_ENDPOINTS:
            raise ValueError('Invalid region: %s' % (region))

        self.selected_region = API_ENDPOINTS[region]

        super(DimensionDataNodeDriver, self).__init__(key=key, secret=secret,
                                                      secure=secure, host=host,
                                                      port=port,
                                                      api_version=api_version,
                                                      region=region,
                                                      **kwargs)

    def _ex_connection_class_kwargs(self):
        """
            Add the region to the kwargs before the connection is instantiated
        """

        kwargs = super(DimensionDataNodeDriver,
                       self)._ex_connection_class_kwargs()
        kwargs['region'] = self.selected_region
        return kwargs

    def create_node(self, name, image, auth, ex_description,
                    ex_network=None, ex_network_domain=None,
                    ex_vlan=None,
                    ex_is_started=True, **kwargs):
        """
        Create a new DimensionData node

        :keyword    name:   String with a name for this new node (required)
        :type       name:   ``str``

        :keyword    image:  OS Image to boot on node. (required)
        :type       image:  :class:`NodeImage`

        :keyword    auth:   Initial authentication information for the
                            node (required)
        :type       auth:   :class:`NodeAuthPassword`

        :keyword    ex_description:  description for this node (required)
        :type       ex_description:  ``str``

        :keyword    ex_network:  Network to create the node within (required,
                                unless using Network Domain)
        :type       ex_network: :class:`DimensionDataNetwork`

        :keyword    ex_network_domain:  Network Domain to create the node
                                        (required unless using network)
        :type       ex_network_domain: :class:`DimensionDataNetworkDomain`

        :keyword    ex_vlan:  VLAN to create the node within
                                        (required unless using network)
        :type       ex_vlan: :class:`DimensionDataVlan`

        :keyword    ex_is_started:  Start server after creation? default
                                   true (required)
        :type       ex_is_started:  ``bool``

        :return: The newly created :class:`Node`.
        :rtype: :class:`Node`
        """

        password = None
        auth_obj = self._get_and_check_auth(auth)
        password = auth_obj.password

        if not isinstance(ex_network, DimensionDataNetwork):
            if not isinstance(ex_network_domain, DimensionDataNetworkDomain):
                raise ValueError('ex_network must be of DimensionDataNetwork '
                                 'type or ex_network_domain must be of '
                                 'DimensionDataNetworkDomain type')

        server_elm = ET.Element('deployServer', {'xmlns': TYPES_URN})
        ET.SubElement(server_elm, "name").text = name
        ET.SubElement(server_elm, "description").text = ex_description
        ET.SubElement(server_elm, "imageId").text = image.id
        ET.SubElement(server_elm, "start").text = str(ex_is_started).lower()
        ET.SubElement(server_elm, "administratorPassword").text = password

        if ex_network is not None:
            network_elm = ET.SubElement(server_elm, "network")
            ET.SubElement(network_elm, "networkId").text = ex_network.id
        if ex_network_domain is not None:
            network_inf_elm = ET.SubElement(server_elm, "networkInfo",
                                            {'networkDomainId':
                                             ex_network_domain.id})
            pri_nic = ET.SubElement(network_inf_elm, "primaryNic")
            ET.SubElement(pri_nic, "vlanId").text = ex_vlan.id

        response = self.connection.request_with_orgId_api_2(
            'server/deployServer',
            method='POST',
            data=ET.tostring(server_elm)).object

        node_id = None
        for info in findall(response, 'info', TYPES_URN):
            if info.get('name') == 'serverId':
                node_id = info.get('value')

        node = self.ex_get_node_by_id(node_id)

        if getattr(auth_obj, "generated", False):
            node.extra['password'] = auth_obj.password

        return node

    def destroy_node(self, node):
        request_elm = ET.Element('deleteServer',
                                 {'xmlns': TYPES_URN, 'id': node.id})
        body = self.connection.request_with_orgId_api_2(
            'server/deleteServer',
            method='POST',
            data=ET.tostring(request_elm)).object
        result = findtext(body, 'responseCode', TYPES_URN)
        return result == 'IN_PROGRESS'

    def reboot_node(self, node):
        request_elm = ET.Element('rebootServer',
                                 {'xmlns': TYPES_URN, 'id': node.id})
        body = self.connection.request_with_orgId_api_2(
            'server/rebootServer',
            method='POST',
            data=ET.tostring(request_elm)).object
        result = findtext(body, 'responseCode', TYPES_URN)
        return result == 'IN_PROGRESS'

    def list_nodes(self):
        nodes = self._to_nodes(
            self.connection.request_with_orgId_api_2('server/server').object)

        return nodes

    def list_images(self, location=None):
        """
        return a list of available images
            Currently only returns the default 'base OS images' provided by
            DimensionData. Customer images (snapshots) are not yet supported.

        @inherits: :class:`NodeDriver.list_images`
        """
        params = {}
        if location is not None:
            params['location'] = location.id

        return self._to_base_images(
            self.connection.request_api_1('base/imageWithDiskSpeed',
                                          params=params)
            .object)

    def list_sizes(self, location=None):
        """
        return a list of available sizes
            Currently, the size of the node is dictated by the chosen OS base
            image, they cannot be set explicitly.

        @inherits: :class:`NodeDriver.list_sizes`
        """
        return [
            NodeSize(id=1,
                     name="default",
                     ram=0,
                     disk=0,
                     bandwidth=0,
                     price=0,
                     driver=self.connection.driver),
        ]

    def list_locations(self):
        """
        list locations (datacenters) available for instantiating servers and
        networks.

        @inherits: :class:`NodeDriver.list_locations`
        """
        return self._to_locations(
            self.connection
            .request_with_orgId_api_2('infrastructure/datacenter').object)

    def list_networks(self, location=None):
        """
        List networks deployed across all data center locations for your
        organization.  The response includes the location of each network.


        :keyword location: The location
        :type    location: :class:`NodeLocation`

        :return: a list of DimensionDataNetwork objects
        :rtype: ``list`` of :class:`DimensionDataNetwork`
        """
        url_ext = ''
        if location is not None:
            url_ext = '/' + location.id

        return self._to_networks(
            self.connection
            .request_with_orgId_api_1('networkWithLocation%s' % url_ext)
            .object)

    def _to_base_images(self, object):
        images = []
        locations = self.list_locations()

        for element in object.findall(fixxpath("image", SERVER_NS)):
            images.append(self._to_base_image(element, locations))

        return images

    def _to_base_image(self, element, locations):
        # Eventually we will probably need multiple _to_image() functions
        # that parse <ServerImage> differently than <DeployedImage>.
        # DeployedImages are customer snapshot images, and ServerImages are
        # 'base' images provided by DimensionData
        location_id = element.get('location')
        location = list(filter(lambda x: x.id == location_id,
                               locations))[0]

        extra = {
            'description': findtext(element, 'description', SERVER_NS),
            'OS_type': findtext(element, 'operatingSystem/type', SERVER_NS),
            'OS_displayName': findtext(element, 'operatingSystem/displayName',
                                       SERVER_NS),
            'cpuCount': findtext(element, 'cpuCount', SERVER_NS),
            'resourcePath': findtext(element, 'resourcePath', SERVER_NS),
            'memory': findtext(element, 'memory', SERVER_NS),
            'osStorage': findtext(element, 'osStorage', SERVER_NS),
            'additionalStorage': findtext(element, 'additionalStorage',
                                          SERVER_NS),
            'created': findtext(element, 'created', SERVER_NS),
            'location': location,
        }

        return NodeImage(id=element.get('id'),
                         name=str(findtext(element, 'name', SERVER_NS)),
                         extra=extra,
                         driver=self.connection.driver)

    def ex_start_node(self, node):
        """
        Powers on an existing deployed server

        :param      node: Node which should be used
        :type       node: :class:`Node`

        :rtype: ``bool``
        """
        request_elm = ET.Element('startServer',
                                 {'xmlns': TYPES_URN, 'id': node.id})
        body = self.connection.request_with_orgId_api_2(
            'server/startServer',
            method='POST',
            data=ET.tostring(request_elm)).object
        result = findtext(body, 'responseCode', TYPES_URN)
        return result == 'IN_PROGRESS'

    def ex_shutdown_graceful(self, node):
        """
        This function will attempt to "gracefully" stop a server by
        initiating a shutdown sequence within the guest operating system.
        A successful response on this function means the system has
        successfully passed the request into the operating system.

        :param      node: Node which should be used
        :type       node: :class:`Node`

        :rtype: ``bool``
        """
        request_elm = ET.Element('shutdownServer',
                                 {'xmlns': TYPES_URN, 'id': node.id})
        body = self.connection.request_with_orgId_api_2(
            'server/shutdownServer',
            method='POST',
            data=ET.tostring(request_elm)).object
        result = findtext(body, 'responseCode', TYPES_URN)
        return result == 'IN_PROGRESS'

    def ex_power_off(self, node):
        """
        This function will abruptly power-off a server.  Unlike
        ex_shutdown_graceful, success ensures the node will stop but some OS
        and application configurations may be adversely affected by the
        equivalent of pulling the power plug out of the machine.

        :param      node: Node which should be used
        :type       node: :class:`Node`

        :rtype: ``bool``
        """
        request_elm = ET.Element('powerOffServer',
                                 {'xmlns': TYPES_URN, 'id': node.id})
        body = self.connection.request_with_orgId_api_2(
            'server/powerOffServer',
            method='POST',
            data=ET.tostring(request_elm)).object
        result = findtext(body, 'responseCode', TYPES_URN)
        return result == 'IN_PROGRESS'

    def ex_reset(self, node):
        """
        This function will abruptly reset a server.  Unlike
        reboot_node, success ensures the node will restart but some OS
        and application configurations may be adversely affected by the
        equivalent of pulling the power plug out of the machine.

        :param      node: Node which should be used
        :type       node: :class:`Node`

        :rtype: ``bool``
        """
        request_elm = ET.Element('resetServer',
                                 {'xmlns': TYPES_URN, 'id': node.id})
        body = self.connection.request_with_orgId_api_2(
            'server/resetServer',
            method='POST',
            data=ET.tostring(request_elm)).object
        result = findtext(body, 'responseCode', TYPES_URN)
        return result == 'IN_PROGRESS'

    def ex_list_networks(self, location=None):
        """
        List networks deployed across all data center locations for your
        organization.  The response includes the location of each network.

        :return: a list of DimensionDataNetwork objects
        :rtype: ``list`` of :class:`DimensionDataNetwork`
        """
        params = {}
        if location is not None:
            params['location'] = location.id

        response = self.connection \
            .request_with_orgId_api_1('networkWithLocation',
                                      params=params).object
        return self._to_networks(response)

    def ex_list_network_domains(self, location=None):
        """
        List networks deployed across all data center locations for your
        organization.  The response includes the location of each network.

        :return: a list of DimensionDataNetwork objects
        :rtype: ``list`` of :class:`DimensionDataNetwork`
        """
        params = {}
        if location is not None:
            params['datacenterId'] = location.id

        response = self.connection \
            .request_with_orgId_api_2('network/networkDomain',
                                      params=params).object
        return self._to_network_domains(response)

    def ex_list_vlans(self, location=None, network_domain=None):
        """
        List VLANs available in a given networkDomain

        :return: a list of DimensionDataVlan objects
        :rtype: ``list`` of :class:`DimensionDataVlan`
        """
        params = {}
        if location is not None:
            params['datacenterId'] = location.id
        if network_domain is not None:
            params['networkDomainId'] = network_domain.id
        response = self.connection.request_with_orgId_api_2('network/vlan',
                                                            params=params) \
                                  .object
        return self._to_vlans(response)

    def ex_get_node_by_id(self, id):
        node = self.connection.request_with_orgId_api_2(
            'server/server/%s' % id).object
        return self._to_node(node)

    def ex_get_location_by_id(self, id):
        """
        Get location by ID.

        :param  id: ID of the node location which should be used
        :type   id: ``str``

        :rtype: :class:`NodeLocation`
        """
        location = None
        if id is not None:
            location = list(
                filter(lambda x: x.id == id, self.list_locations()))[0]
        return location

    def _to_networks(self, object):
        networks = []
        locations = self.list_locations()
        for element in findall(object, 'network', NETWORK_NS):
            networks.append(self._to_network(element, locations))

        return networks

    def _to_network(self, element, locations):
        multicast = False
        if findtext(element, 'multicast', NETWORK_NS) == 'true':
            multicast = True

        status = self._to_status(element.find(fixxpath('status', NETWORK_NS)))

        location_id = findtext(element, 'location', NETWORK_NS)
        location = list(filter(lambda x: x.id == location_id,
                               locations))[0]

        return DimensionDataNetwork(
            id=findtext(element, 'id', NETWORK_NS),
            name=findtext(element, 'name', NETWORK_NS),
            description=findtext(element, 'description',
                                 NETWORK_NS),
            location=location,
            private_net=findtext(element, 'privateNet',
                                 NETWORK_NS),
            multicast=multicast,
            status=status)

    def _to_network_domains(self, object):
        network_domains = []
        locations = self.list_locations()
        for element in findall(object, 'networkDomain', TYPES_URN):
            network_domains.append(self._to_network_domain(element, locations))

        return network_domains

    def _to_network_domain(self, element, locations):
        status = self._to_status(element.find(fixxpath('state', TYPES_URN)))

        location_id = element.get('datacenterId')
        location = list(filter(lambda x: x.id == location_id,
                               locations))[0]

        return DimensionDataNetworkDomain(
            id=element.get('id'),
            name=findtext(element, 'name', TYPES_URN),
            description=findtext(element, 'description',
                                 TYPES_URN),
            location=location,
            status=status)

    def _to_vlans(self, object):
        vlans = []
        locations = self.list_locations()
        for element in findall(object, 'vlan', TYPES_URN):
            vlans.append(self._to_vlan(element, locations=locations))

        return vlans

    def _to_vlan(self, element, locations):
        status = self._to_status(element.find(fixxpath('state', TYPES_URN)))

        location_id = element.get('datacenterId')
        location = list(filter(lambda x: x.id == location_id,
                               locations))[0]

        return DimensionDataVlan(
            id=element.get('id'),
            name=findtext(element, 'name', TYPES_URN),
            description=findtext(element, 'description',
                                 TYPES_URN),
            location=location,
            status=status)

    def _to_locations(self, object):
        locations = []
        for element in object.findall(fixxpath('datacenter', TYPES_URN)):
            locations.append(self._to_location(element))

        return locations

    def _to_location(self, element):
        l = NodeLocation(id=element.get('id'),
                         name=findtext(element, 'displayName', TYPES_URN),
                         country=findtext(element, 'country', TYPES_URN),
                         driver=self)
        return l

    def _to_nodes(self, object):
        node_elements = object.findall(fixxpath('Server', TYPES_URN))

        return [self._to_node(el) for el in node_elements]

    def _to_node(self, element):
        if findtext(element, 'started', TYPES_URN) == 'true':
            state = NodeState.RUNNING
        else:
            state = NodeState.TERMINATED

        status = self._to_status(element.find(fixxpath('progress', TYPES_URN)))

        has_network_info \
            = element.find(fixxpath('networkInfo', TYPES_URN)) is not None

        extra = {
            'description': findtext(element, 'description', TYPES_URN),
            'sourceImageId': findtext(element, 'sourceImageId', TYPES_URN),
            'networkId': findtext(element, 'networkId', TYPES_URN),
            'networkDomainId':
                element.find(fixxpath('networkInfo', TYPES_URN))
                .get('networkDomainId')
                if has_network_info else None,
            'datacenterId': element.get('datacenterId'),
            'deployedTime': findtext(element, 'createTime', TYPES_URN),
            'cpuCount': int(findtext(
                element,
                'cpuCount',
                TYPES_URN)),
            'memoryMb': int(findtext(
                element,
                'memoryGb',
                TYPES_URN)) * 1024,
            'OS_id': element.find(fixxpath(
                'operatingSystem',
                TYPES_URN)).get('id'),
            'OS_type': element.find(fixxpath(
                'operatingSystem',
                TYPES_URN)).get('family'),
            'OS_displayName': element.find(fixxpath(
                'operatingSystem',
                TYPES_URN)).get('displayName'),
            'status': status
        }

        public_ip = findtext(element, 'publicIpAddress', TYPES_URN)

        private_ip = element.find(
            fixxpath('networkInfo/primaryNic', TYPES_URN)) \
            .get('privateIpv4') \
            if has_network_info else \
            element.find(fixxpath('nic', TYPES_URN)).get('privateIpv4')

        n = Node(id=element.get('id'),
                 name=findtext(element, 'name', TYPES_URN),
                 state=state,
                 public_ips=[public_ip] if public_ip is not None else [],
                 private_ips=[private_ip] if private_ip is not None else [],
                 driver=self.connection.driver,
                 extra=extra)
        return n

    def _to_status(self, element):
        if element is None:
            return DimensionDataStatus()
        s = DimensionDataStatus(action=findtext(element, 'action', TYPES_URN),
                                request_time=findtext(
                                    element,
                                    'requestTime',
                                    TYPES_URN),
                                user_name=findtext(
                                    element,
                                    'userName',
                                    TYPES_URN),
                                number_of_steps=findtext(
                                    element,
                                    'numberOfSteps',
                                    TYPES_URN),
                                step_name=findtext(
                                    element,
                                    'step/name',
                                    TYPES_URN),
                                step_number=findtext(
                                    element,
                                    'step_number',
                                    TYPES_URN),
                                step_percent_complete=findtext(
                                    element,
                                    'step/percentComplete',
                                    TYPES_URN),
                                failure_reason=findtext(
                                    element,
                                    'failureReason',
                                    TYPES_URN))
        return s
