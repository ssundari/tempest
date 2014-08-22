import random
import netaddr
from tempest.api.network import base
from tempest import config
from tempest import test
from tempest.openstack.common import log as logging
from tempest.common.utils.data_utils import get_ipv6_addr_by_EUI64, \
    rand_mac_address
from tempest import exceptions

CONF = config.CONF
LOG = logging.getLogger(__name__)


class NetworksTestDHCPv6JSON(base.BaseNetworkTest):
    _interface = 'json'
    _ip_version = 6

    @classmethod
    @test.safe_setup
    def setUpClass(cls):
        super(NetworksTestDHCPv6JSON, cls).setUpClass()
        cls.network = cls.create_network()

    def _clean_network(self, **kwargs):
        if "ports" in kwargs:
            for port in kwargs["ports"]:
                self.client.delete_port(port['id'])
        if "router_interfaces" in kwargs:
            for interface in kwargs["router_interfaces"]:
                self.client.remove_router_interface_with_subnet_id(*interface)
        if "subnets" in kwargs:
            for subnet in kwargs["subnets"]:
                self.client.delete_subnet(subnet['id'])
        if "routers" in kwargs:
            for router in kwargs["routers"]:
                self.client.delete_router(router['id'])

    @test.attr(type='smoke')
    def test_dhcpv6_stateless_eui64(self):
        """When subnets configured with RAs SLAAC (AOM=100) and DHCP stateless
        (AOM=110) both for radvd and dnsmasq, port shall receive IP address
        calculated from its MAC.
        """
        for ra_mode, add_mode in (
                ('slaac', 'slaac'),
                ('dhcpv6-stateless', 'dhcpv6-stateless'),
        ):
            kwargs = {'ipv6_ra_mode': ra_mode,
                      'ipv6_address_mode': add_mode}
            subnet = self.create_subnet(self.network, **kwargs)
            self.subnets.pop()
            port_mac = rand_mac_address()
            port = self.create_port(self.network, mac_address=port_mac)
            self.ports.pop()
            real_ip = next(iter(port['fixed_ips']))['ip_address']
            eui_ip = get_ipv6_addr_by_EUI64(subnet['cidr'], port_mac).format()
            self._clean_network(ports=[port], subnets=[subnet])
            self.assertEqual(eui_ip, real_ip,
                             ('Real port IP is %s, but shall be %s when '
                              'ipv6_ra_mode=%s and ipv6_address_mode=%s') % (
                                 real_ip, eui_ip, ra_mode, add_mode))

    @test.attr(type='smoke')
    def test_dhcpv6_stateless_only_ra(self):
        """When subnets configured with RAs SLAAC (AOM=100) and DHCP stateless
        (AOM=110) for radvd and dnsmasq is not configured, port shall receive
        IP address calculated from its MAC and mask advertised from RAs
        """
        for ra_mode, add_mode in (
                ('slaac', None),
                ('dhcpv6-stateless', None),
        ):
            kwargs = {'ipv6_ra_mode': ra_mode,
                      'ipv6_address_mode': add_mode}
            kwargs = {k: v for k, v in kwargs.iteritems() if v}
            subnet = self.create_subnet(self.network, **kwargs)
            self.subnets.pop()
            router = self.create_router(router_name="router1",
                                        admin_state_up=True)
            self.create_router_interface(router['id'],
                                         subnet['id'])
            self.routers.pop()
            port_mac = rand_mac_address()
            port = self.create_port(self.network, mac_address=port_mac)
            self.ports.pop()
            real_ip = next(iter(port['fixed_ips']))['ip_address']
            eui_ip = get_ipv6_addr_by_EUI64(subnet['cidr'], port_mac).format()
            self._clean_network(ports=[port],
                                subnets=[subnet],
                                router_interfaces=[(router['id'],
                                                    subnet['id'])],
                                routers=[router])
            self.assertEqual(eui_ip, real_ip,
                             ('Real port IP is %s, but shall be %s when '
                              'ipv6_ra_mode=%s and ipv6_address_mode=%s') % (
                                 real_ip,
                                 eui_ip,
                                 ra_mode if ra_mode else "Off",
                                 add_mode if add_mode else "Off"))

    @test.attr(type='smoke')
    def test_dhcpv6_stateless_no_ra(self):
        """When subnets configured with dnsmasq SLAAC and DHCP stateless
        and there is no radvd, port shall receive IP address calculated
        from its MAC and mask of subnet.
        """
        for ra_mode, add_mode in (
                (None, 'slaac'),
                (None, 'dhcpv6-stateless'),
        ):
            kwargs = {'ipv6_ra_mode': ra_mode,
                      'ipv6_address_mode': add_mode}
            kwargs = {k: v for k, v in kwargs.iteritems() if v}
            subnet = self.create_subnet(self.network, **kwargs)
            self.subnets.pop()
            port_mac = rand_mac_address()
            port = self.create_port(self.network, mac_address=port_mac)
            self.ports.pop()
            real_ip = next(iter(port['fixed_ips']))['ip_address']
            eui_ip = get_ipv6_addr_by_EUI64(subnet['cidr'], port_mac).format()
            self._clean_network(ports=[port], subnets=[subnet])
            self.assertEqual(eui_ip, real_ip,
                             ('Real port IP %s equal to EUI-64 %s when '
                              'ipv6_ra_mode=%s and ipv6_address_mode=%s') % (
                                 real_ip, eui_ip,
                                 ra_mode if ra_mode else "Off",
                                 add_mode if add_mode else "Off"))

    @test.attr(type='smoke')
    def test_dhcpv6_invalid_options(self):
        """Different configurations for radvd and dnsmasq are not allowed"""
        for ra_mode, add_mode in (
                ('dhcpv6-stateless', 'dhcpv6-stateful'),
                ('dhcpv6-stateless', 'slaac'),
                ('slaac', 'dhcpv6-stateful'),
                ('dhcpv6-stateful', 'dhcpv6-stateless'),
                ('dhcpv6-stateful', 'slaac'),
                ('slaac', 'dhcpv6-stateless'),
        ):
            kwargs = {'ipv6_ra_mode': ra_mode,
                      'ipv6_address_mode': add_mode}
            self.assertRaises(exceptions.BadRequest,
                              self.create_subnet,
                              self.network,
                              **kwargs)

    @test.attr(type='smoke')
    def test_dhcpv6_stateless_no_ra_no_dhcp(self):
        """If no radvd option and no dnsmasq option is configured
        port shall receive IP from fixed IPs list of subnet.
        """
        subnet = self.create_subnet(self.network)
        self.subnets.pop()
        port_mac = rand_mac_address()
        port = self.create_port(self.network, mac_address=port_mac)
        self.ports.pop()
        real_ip = next(iter(port['fixed_ips']))['ip_address']
        eui_ip = get_ipv6_addr_by_EUI64(subnet['cidr'], port_mac).format()
        self._clean_network(ports=[port], subnets=[subnet])
        self.assertNotEqual(eui_ip, real_ip,
                            ('Real port IP %s equal to EUI-64 %s when '
                             'ipv6_ra_mode=Off and ipv6_address_mode=Off') % (
                                real_ip, eui_ip))

    @test.attr(type='smoke')
    def test_dhcpv6_stateless_two_subnets(self):
        """When 2 subnets configured with dnsmasq SLAAC and DHCP stateless
        and there is radvd, port shall receive IP addresses calculated
        from its MAC and mask of subnet from both subnets.
        """
        for ra_mode, add_mode in (
                ('slaac', 'slaac'),
                ('dhcpv6-stateless', 'dhcpv6-stateless'),
        ):
            kwargs = {'ipv6_ra_mode': ra_mode,
                      'ipv6_address_mode': add_mode}
            subnet1 = self.create_subnet(self.network, **kwargs)
            self.subnets.pop()
            subnet2 = self.create_subnet(self.network, **kwargs)
            self.subnets.pop()
            port_mac = rand_mac_address()
            port = self.create_port(self.network, mac_address=port_mac)
            self.ports.pop()
            real_ips = [i['ip_address'] for i in port['fixed_ips']]
            eui_ips = [
                get_ipv6_addr_by_EUI64(i['cidr'], port_mac).format()
                for i in (subnet1, subnet2)
            ]
            self._clean_network(ports=[port], subnets=[subnet1, subnet2])
            self.assertSequenceEqual(sorted(real_ips), sorted(eui_ips),
                                     ('Real port IPs %s and %s are not equal to'
                                      ' SLAAC IPs %s %s') % tuple(real_ips + eui_ips))

    @test.attr(type='smoke')
    def test_dhcpv6_two_subnets(self):
        """When one subnet configured with dnsmasq SLAAC or DHCP stateless
        and other is with DHCP stateful, port shall receive EUI-64 IP
        addresses from first subnet and DHCP address from second one.
        Order of subnet creating should be unimportant.
        """
        for order in ("slaac_first", "dhcp_first"):
            for ra_mode, add_mode in (
                    ('slaac', 'slaac'),
                    ('dhcpv6-stateless', 'dhcpv6-stateless'),
            ):
                kwargs = {'ipv6_ra_mode': ra_mode,
                          'ipv6_address_mode': add_mode}
                kwargs_dhcp = {'ipv6_address_mode': 'dhcpv6-stateful'}
                if order == "slaac_first":
                    subnet_slaac = self.create_subnet(self.network, **kwargs)
                    subnet_dhcp = self.create_subnet(self.network, **kwargs_dhcp)
                else:
                    subnet_dhcp = self.create_subnet(self.network, **kwargs_dhcp)
                    subnet_slaac = self.create_subnet(self.network, **kwargs)
                port_mac = rand_mac_address()
                port = self.create_port(self.network, mac_address=port_mac)
                real_ips = dict([(k['subnet_id'], k['ip_address'])
                                 for k in port['fixed_ips']])
                real_dhcp_ip, real_eui_ip = [real_ips[sub['id']]
                                             for sub in subnet_dhcp, subnet_slaac]
                dhcp_ip = subnet_dhcp["allocation_pools"][0]["start"]
                eui_ip = get_ipv6_addr_by_EUI64(
                    subnet_slaac['cidr'],
                    port_mac
                ).format()
                self.subnets.pop()
                self.subnets.pop()
                self.ports.pop()
                self._clean_network(ports=[port],
                                    subnets=[subnet_slaac, subnet_dhcp])
                self.assertSequenceEqual((real_eui_ip, real_dhcp_ip),
                                         (eui_ip, dhcp_ip),
                                         ('Real port IPs %s and %s are not equal'
                                          ' to planned IPs %s %s') % (
                                             real_dhcp_ip,
                                             real_eui_ip,
                                             eui_ip,
                                             dhcp_ip))

    @test.attr(type='smoke')
    def test_slaac_duplicate(self):
        """When creating SLAAC address, neutron shall check
        that there are not any duplicates of this address in
        the network.
        """
        kwargs = {'ipv6_ra_mode': 'slaac',
                  'ipv6_address_mode': 'slaac'}
        subnet = self.create_subnet(self.network, **kwargs)
        port_mac = rand_mac_address()
        eui_ip = get_ipv6_addr_by_EUI64(subnet['cidr'], port_mac).format()
        port = self.create_port(self.network,
                                fixed_ips=[
                                    {'subnet_id': subnet['id'],
                                     'ip_address': eui_ip}])
        port_ip = next(iter(port['fixed_ips']))['ip_address']
        self.assertEqual(port_ip, eui_ip, "IP is not EUI-64: %s" % port_ip)
        self.assertRaisesRegexp(
            exceptions.Conflict,
            "An object with that identifier already exists",
            self.create_port,
            self.network,
            mac_address=port_mac)

    @test.attr(type='smoke')
    def test_dhcp_stateful(self):
        """When all options below, DHCPv6 shall allocate first
        address from subnet pool to port..
        """
        for ra_mode, add_mode in (
                ('dhcpv6-stateful', 'dhcpv6-stateful'),
                ('dhcpv6-stateful', None),
                (None, 'dhcpv6-stateful'),
        ):
            kwargs = {'ipv6_ra_mode': ra_mode,
                      'ipv6_address_mode': add_mode}
            kwargs = {k: v for k, v in kwargs.iteritems() if v}
            subnet = self.create_subnet(self.network, **kwargs)
            self.subnets.pop()
            port = self.create_port(self.network,)
            self.ports.pop()
            port_ip = next(iter(port['fixed_ips']))['ip_address']
            first_alloc = subnet["allocation_pools"][0]["start"]
            self._clean_network(ports=[port], subnets=[subnet])
            self.assertEqual(port_ip, first_alloc,
                             ("Port IP %s is not as first IP from "
                              "subnets allocation pool: %s") % (
                                 port_ip, first_alloc))

    @test.attr(type='smoke')
    def test_dhcp_stateful_fixedips(self):
        """When all options below, port shall be able to get
        requested IP from fixed IP range not depending on
        DHCP settings configured..
        """
        for ra_mode, add_mode in (
                ('dhcpv6-stateful', 'dhcpv6-stateful'),
                ('dhcpv6-stateful', None),
                (None, 'dhcpv6-stateful'),
                ('slaac', 'slaac'),
                ('dhcpv6-stateless', 'dhcpv6-stateless'),
                (None, 'slaac'),
                (None, 'dhcpv6-stateless'),
                ('slaac', None),
                ('dhcpv6-stateless', None),
        ):
            kwargs = {'ipv6_ra_mode': ra_mode,
                      'ipv6_address_mode': add_mode}
            kwargs = {k: v for k, v in kwargs.iteritems() if v}
            subnet = self.create_subnet(self.network, **kwargs)
            self.subnets.pop()
            ip_range = netaddr.IPRange(subnet["allocation_pools"][0]["start"],
                               subnet["allocation_pools"][0]["end"])
            ip = netaddr.IPAddress(random.randrange(ip_range.first,
                                                    ip_range.last)).format()
            port = self.create_port(self.network,
                                fixed_ips=[
                                    {'subnet_id': subnet['id'],
                                     'ip_address': ip}])
            self.ports.pop()
            port_ip = next(iter(port['fixed_ips']))['ip_address']
            self._clean_network(ports=[port], subnets=[subnet])
            self.assertEqual(port_ip, ip,
                             ("Port IP %s is not as fixed IP from "
                              "port create request: %s") % (
                                 port_ip, ip))

    @test.attr(type='smoke')
    def test_dhcp_stateful_fixedips_outrange(self):
        """When port gets IP address from fixed IP range it
        shall be checked if it's from subnets range.
        """
        kwargs = {'ipv6_ra_mode': 'dhcpv6-stateful',
                  'ipv6_address_mode': 'dhcpv6-stateful'}
        subnet = self.create_subnet(self.network, **kwargs)
        ip_range = netaddr.IPRange(subnet["allocation_pools"][0]["start"],
                           subnet["allocation_pools"][0]["end"])
        ip = netaddr.IPAddress(random.randrange(
            ip_range.last+1, ip_range.last+10)).format()
        self.assertRaisesRegexp(exceptions.BadRequest,
                                "not a valid IP for the defined subnet",
                                self.create_port,
                                self.network,
                                fixed_ips=[{'subnet_id': subnet['id'],
                                            'ip_address': ip}])

    @test.attr(type='smoke')
    def test_dhcp_stateful_fixedips_duplicate(self):
        """When port gets IP address from fixed IP range it
        shall be checked if it's not duplicate.
        """
        kwargs = {'ipv6_ra_mode': 'dhcpv6-stateful',
                  'ipv6_address_mode': 'dhcpv6-stateful'}
        subnet = self.create_subnet(self.network, **kwargs)
        ip_range = netaddr.IPRange(subnet["allocation_pools"][0]["start"],
                           subnet["allocation_pools"][0]["end"])
        ip = netaddr.IPAddress(random.randrange(
            ip_range.first, ip_range.last)).format()
        self.create_port(self.network,
                         fixed_ips=[
                             {'subnet_id': subnet['id'],
                              'ip_address': ip}])
        self.assertRaisesRegexp(exceptions.Conflict,
                                "object with that identifier already exists",
                                self.create_port,
                                self.network,
                                fixed_ips=[{'subnet_id': subnet['id'],
                                            'ip_address': ip}])


class NetworksTestDHCPv6XML(NetworksTestDHCPv6JSON):
    _interface = 'xml'
